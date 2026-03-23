"""Patch executor – converts PatchPlan into workspace file operations.

Strategies:
  create          – LLM generates new screen/component from scratch
  update          – LLM rewrites an entire file with modifications
  targeted-update – LLM patches only the selected region (constrained)
  rollback        – restores files from backup
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional
from uuid import uuid4

from .build_validator import ValidationResult, validate_files
from .file_service import (
    backup_file,
    cleanup_backup,
    file_exists,
    list_files,
    read_file,
    restore_from_backup,
    write_file,
)
from .models import (
    DesignIntent,
    PatchPlan,
    PatchRecord,
    PatchTarget,
    ProjectManifest,
    SelectedElement,
    utc_now,
)
from .providers import ProviderClient


# ── Marker constants ───────────────────────────────────────────────────────

REGION_START = "<!-- @lfg-region:{name} -->"
REGION_END = "<!-- @lfg-region-end:{name} -->"
COMPONENT_ATTR = 'data-lfg-component="{name}"'
REGION_PATTERN = re.compile(
    r"<!-- @lfg-region:(?P<name>[A-Za-z0-9_-]+) -->(?P<content>.*?)<!-- @lfg-region-end:(?P=name) -->",
    re.DOTALL,
)


def inject_markers(html: str, component_name: str) -> str:
    """Wrap *html* in region markers if they are not already present."""
    marker_start = REGION_START.format(name=component_name)
    if marker_start in html:
        return html
    marker_end = REGION_END.format(name=component_name)
    return f"{marker_start}\n{html}\n{marker_end}"


def extract_region(file_content: str, region_name: str) -> Optional[str]:
    """Return the inner content of a named region, or None if not found."""
    match = REGION_PATTERN.search(file_content.replace(region_name, region_name))
    for m in REGION_PATTERN.finditer(file_content):
        if m.group("name") == region_name:
            return m.group("content")
    return None


def replace_region(file_content: str, region_name: str, new_inner: str) -> str:
    """Replace the content inside a named region, preserving markers."""
    def _replacer(m: re.Match) -> str:
        if m.group("name") == region_name:
            return (
                f"<!-- @lfg-region:{region_name} -->\n"
                f"{new_inner.strip()}\n"
                f"<!-- @lfg-region-end:{region_name} -->"
            )
        return m.group(0)

    return REGION_PATTERN.sub(_replacer, file_content)


# ── LLM prompt builders ───────────────────────────────────────────────────

def _system_prompt_create(design_intent: DesignIntent, manifest: ProjectManifest) -> str:
    return f"""You are a UI code generator for a local AI-native UI workspace.
Generate a complete, self-contained HTML page section or component.

Design intent:
- Objective: {design_intent.objective}
- Screen type: {design_intent.screenType}
- Layout direction: {design_intent.layout.direction}
- Density: {design_intent.layout.density}
- Regions: {', '.join(design_intent.layout.regions)}
- Tone: {', '.join(design_intent.tone)}
- Style references: {', '.join(r.label for r in design_intent.styleReferences) if design_intent.styleReferences else 'none'}
- Constraints: {'; '.join(design_intent.lockedConstraints) if design_intent.lockedConstraints else 'none'}

Rules:
1. Output ONLY valid HTML/CSS/JS – no markdown fences, no explanations.
2. Use inline <style> and <script> tags within the HTML.
3. Wrap each logical UI section with region markers:
   <!-- @lfg-region:SectionName -->
   <div data-lfg-component="SectionName">...</div>
   <!-- @lfg-region-end:SectionName -->
4. Use modern CSS (flexbox/grid). Make it visually polished.
5. The page must be fully self-contained – no external JS frameworks.
6. Include a <title> and proper <meta> tags.
7. DEMO INTERACTIVITY (CRITICAL): Every interactive element MUST have working JavaScript event handlers.
   - Buttons: attach click handlers that perform a visible demo action (e.g. show a toast/notification, toggle state, append content, navigate between views, open/close modals).
   - Input fields / text areas: handle Enter key or submit to display the user's input as a response (e.g. chat messages, search results placeholder).
   - Navigation tabs / links: switch visible content panels or highlight the active tab.
   - "New Chat" / "New Conversation" buttons: clear the current conversation area and reset to the initial state.
   - Suggestion chips / quick-action buttons: simulate clicking by inserting the chip text into the input and triggering a demo response.
   - The page must feel alive — clicking any button should produce an immediate, visible result so users can understand how the UI works.
   - Use vanilla JS (addEventListener or onclick) — no frameworks.
"""


def _system_prompt_targeted_update(
    existing_code: str,
    region_content: Optional[str],
    selected_element: Optional[SelectedElement],
    design_intent: DesignIntent,
) -> str:
    selection_ctx = ""
    if selected_element:
        selection_ctx = f"""
Selection context:
- Selector: {selected_element.selector}
- Component hint: {selected_element.componentHint or 'none'}
- Text snippet: {selected_element.textSnippet or 'none'}
- Note: {selected_element.note or 'none'}
- Source hint file: {selected_element.sourceHint.filePath if selected_element.sourceHint else 'none'}
"""
    region_ctx = ""
    if region_content is not None:
        region_ctx = f"""
Current region content to modify:
```html
{region_content}
```
"""
    return f"""You are a UI code editor for a local AI-native UI workspace.
You must produce a CONSTRAINED PATCH – modify only the targeted component or region.

{selection_ctx}
{region_ctx}
Modification request: {design_intent.objective}

Full file context (read-only reference):
```html
{existing_code[:8000]}
```

Rules:
1. Output ONLY the modified HTML fragment for this region/component.
2. Do NOT output the full file – only the patched section.
3. Preserve region markers: <!-- @lfg-region:Name --> and <!-- @lfg-region-end:Name -->
4. Preserve data-lfg-component attributes.
5. Keep all code outside the targeted region unchanged.
6. No markdown fences, no explanations.
7. If you add new sub-components, wrap them with their own region markers.
8. DEMO INTERACTIVITY: If the modification adds or involves interactive elements (buttons, inputs, tabs, chips), ensure they have working JavaScript event handlers that produce visible demo actions (e.g. toast, toggle, append content, switch tabs). Use vanilla JS — no frameworks.
9. CRITICAL: Make the MINIMUM change necessary. If the request is to change text, ONLY change the text – do NOT alter styles, layout, structure, classes, colors, or any other attributes.
9. Preserve ALL existing inline styles, CSS classes, background colors, gradients, fonts, and visual properties EXACTLY as they are unless the user explicitly asks to change them.
10. When in doubt, change LESS rather than MORE.
"""


def _system_prompt_update(
    existing_code: str,
    design_intent: DesignIntent,
) -> str:
    return f"""You are a UI code editor for a local AI-native UI workspace.
Modify the existing page according to the request.

Current file:
```html
{existing_code[:8000]}
```

Modification request: {design_intent.objective}

Rules:
1. Output the COMPLETE modified HTML file.
2. Preserve ALL existing <!-- @lfg-region:Name --> markers.
3. Preserve data-lfg-component attributes.
4. Add region markers to any new sections you create.
5. No markdown fences, no explanations – output only the HTML.
6. DEMO INTERACTIVITY (CRITICAL): Every interactive element MUST have working JavaScript event handlers.
   - Buttons: attach click handlers that perform a visible demo action (e.g. show a toast/notification, toggle state, append content, navigate between views, open/close modals).
   - Input fields / text areas: handle Enter key or submit to display the user's input as a response (e.g. chat messages, search results placeholder).
   - Navigation tabs / links: switch visible content panels or highlight the active tab.
   - "New Chat" / "New Conversation" buttons: clear the current conversation area and reset to the initial state.
   - Suggestion chips / quick-action buttons: simulate clicking by inserting the chip text into the input and triggering a demo response.
   - The page must feel alive — clicking any button should produce an immediate, visible result so users can understand how the UI works.
   - Use vanilla JS (addEventListener or onclick) — no frameworks.
"""


# ── Core execution ─────────────────────────────────────────────────────────


@dataclass
class PatchExecutionResult:
    record: PatchRecord
    validation: ValidationResult
    files_written: list[str] = field(default_factory=list)
    rollback_performed: bool = False
    error: Optional[str] = None


def _detect_region_for_selection(
    file_content: str,
    selected_element: Optional[SelectedElement],
) -> Optional[str]:
    """Try to find which region marker encloses the selected element.

    Strategies (in priority order):
    1. sourceHint.exportName (set by source_mapper or overlay)
    2. componentHint from data-lfg-component
    3. DOM path component names (e.g. div[Hero])
    4. selector substring match in region content
    5. textSnippet match in region content
    """
    if not selected_element:
        return None

    # 1. Explicit exportName from source mapping
    if (
        selected_element.sourceHint
        and selected_element.sourceHint.exportName
        and extract_region(file_content, selected_element.sourceHint.exportName) is not None
    ):
        return selected_element.sourceHint.exportName

    # 2. Component hint (from data-lfg-component attribute)
    if selected_element.componentHint:
        region = extract_region(file_content, selected_element.componentHint)
        if region is not None:
            return selected_element.componentHint

    # 3. DOM path component names
    if selected_element.domPath:
        for segment in reversed(selected_element.domPath):
            bracket_match = re.search(r'\[([A-Za-z0-9_-]+)\]', segment)
            if bracket_match:
                name = bracket_match.group(1)
                if extract_region(file_content, name) is not None:
                    return name

    # 4. Selector substring match in region content
    if selected_element.selector:
        # Check for data-lfg-component in selector
        attr_match = re.search(r'data-lfg-component="([^"]+)"', selected_element.selector)
        if attr_match:
            name = attr_match.group(1)
            if extract_region(file_content, name) is not None:
                return name

        for m in REGION_PATTERN.finditer(file_content):
            region_inner = m.group("content")
            # Check if selector elements appear in region
            if selected_element.selector in region_inner:
                return m.group("name")

    # 5. Text snippet match
    if selected_element.textSnippet and len(selected_element.textSnippet) > 5:
        snippet = selected_element.textSnippet[:80]
        for m in REGION_PATTERN.finditer(file_content):
            if snippet in m.group("content"):
                return m.group("name")

    return None


def _strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences if the LLM wraps its output."""
    text = text.strip()
    if text.startswith("```"):
        first_nl = text.index("\n") if "\n" in text else len(text)
        text = text[first_nl + 1:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def execute_create(
    plan: PatchPlan,
    design_intent: DesignIntent,
    manifest: ProjectManifest,
    provider_client: ProviderClient,
) -> PatchExecutionResult:
    """Generate a new page/screen from scratch."""
    record_id = f"rec-{uuid4().hex[:8]}"
    target_file = "preview/index.html"
    files_written: list[str] = []

    # Backup existing file
    backup_file(target_file, plan.id)

    prompt = _system_prompt_create(design_intent, manifest)
    try:
        generated = provider_client.complete_text(prompt)
        generated = _strip_markdown_fences(generated)
    except Exception as exc:
        restore_from_backup(target_file, plan.id)
        return PatchExecutionResult(
            record=PatchRecord(
                id=record_id,
                sessionId=plan.sessionId,
                planId=plan.id,
                status="failed",
                filesChanged=[],
                summary=f"LLM generation failed: {exc}",
                createdAt=utc_now(),
            ),
            validation=ValidationResult(ok=False, errors=[str(exc)]),
            error=str(exc),
        )

    write_file(target_file, generated)
    files_written.append(target_file)

    # Validate
    validation = validate_files(files_written)

    if not validation.ok:
        # Rollback
        restore_from_backup(target_file, plan.id)
        return PatchExecutionResult(
            record=PatchRecord(
                id=record_id,
                sessionId=plan.sessionId,
                planId=plan.id,
                status="failed",
                filesChanged=files_written,
                summary=f"Validation failed: {'; '.join(validation.errors)}",
                createdAt=utc_now(),
            ),
            validation=validation,
            rollback_performed=True,
            files_written=files_written,
            error=f"Validation failed: {'; '.join(validation.errors)}",
        )

    cleanup_backup(plan.id)

    return PatchExecutionResult(
        record=PatchRecord(
            id=record_id,
            sessionId=plan.sessionId,
            planId=plan.id,
            status="applied",
            filesChanged=files_written,
            summary=f"Created new {design_intent.screenType} screen",
            createdAt=utc_now(),
        ),
        validation=validation,
        files_written=files_written,
    )


def execute_targeted_update(
    plan: PatchPlan,
    design_intent: DesignIntent,
    manifest: ProjectManifest,
    selected_element: Optional[SelectedElement],
    provider_client: ProviderClient,
) -> PatchExecutionResult:
    """Modify only the targeted region/component."""
    record_id = f"rec-{uuid4().hex[:8]}"

    # Determine target file
    target_file = (
        plan.target.files[0] if plan.target.files
        else "preview/index.html"
    )
    if not file_exists(target_file):
        return PatchExecutionResult(
            record=PatchRecord(
                id=record_id,
                sessionId=plan.sessionId,
                planId=plan.id,
                status="failed",
                filesChanged=[],
                summary=f"Target file not found: {target_file}",
                createdAt=utc_now(),
            ),
            validation=ValidationResult(ok=False, errors=[f"File not found: {target_file}"]),
            error=f"Target file not found: {target_file}",
        )

    existing_code = read_file(target_file)
    backup_file(target_file, plan.id)
    files_written: list[str] = []

    # Try to find the target region
    region_name = _detect_region_for_selection(existing_code, selected_element)
    region_content = extract_region(existing_code, region_name) if region_name else None

    prompt = _system_prompt_targeted_update(
        existing_code, region_content, selected_element, design_intent
    )

    try:
        patched_fragment = provider_client.complete_text(prompt)
        patched_fragment = _strip_markdown_fences(patched_fragment)
    except Exception as exc:
        restore_from_backup(target_file, plan.id)
        return PatchExecutionResult(
            record=PatchRecord(
                id=record_id,
                sessionId=plan.sessionId,
                planId=plan.id,
                status="failed",
                filesChanged=[],
                summary=f"LLM patch generation failed: {exc}",
                createdAt=utc_now(),
            ),
            validation=ValidationResult(ok=False, errors=[str(exc)]),
            error=str(exc),
        )

    # Apply the patch
    if region_name and region_content is not None:
        # Constrained: replace only the target region
        new_content = replace_region(existing_code, region_name, patched_fragment)
    else:
        # Fallback: LLM returned a fragment, try to locate and replace
        # or treat as a full-file update if no region boundaries found
        if REGION_PATTERN.search(existing_code):
            # File has regions but we couldn't match – safer to do full update
            update_prompt = _system_prompt_update(existing_code, design_intent)
            try:
                new_content = provider_client.complete_text(update_prompt)
                new_content = _strip_markdown_fences(new_content)
            except Exception as exc:
                restore_from_backup(target_file, plan.id)
                return PatchExecutionResult(
                    record=PatchRecord(
                        id=record_id,
                        sessionId=plan.sessionId,
                        planId=plan.id,
                        status="failed",
                        filesChanged=[],
                        summary=f"Fallback update failed: {exc}",
                        createdAt=utc_now(),
                    ),
                    validation=ValidationResult(ok=False, errors=[str(exc)]),
                    error=str(exc),
                )
        else:
            # No region markers at all – wrap the patched output and do full update
            update_prompt = _system_prompt_update(existing_code, design_intent)
            try:
                new_content = provider_client.complete_text(update_prompt)
                new_content = _strip_markdown_fences(new_content)
            except Exception as exc:
                restore_from_backup(target_file, plan.id)
                return PatchExecutionResult(
                    record=PatchRecord(
                        id=record_id,
                        sessionId=plan.sessionId,
                        planId=plan.id,
                        status="failed",
                        filesChanged=[],
                        summary=f"Fallback update failed: {exc}",
                        createdAt=utc_now(),
                    ),
                    validation=ValidationResult(ok=False, errors=[str(exc)]),
                    error=str(exc),
                )

    write_file(target_file, new_content)
    files_written.append(target_file)

    validation = validate_files(files_written)

    if not validation.ok:
        restore_from_backup(target_file, plan.id)
        return PatchExecutionResult(
            record=PatchRecord(
                id=record_id,
                sessionId=plan.sessionId,
                planId=plan.id,
                status="failed",
                filesChanged=files_written,
                summary=f"Validation failed after patch: {'; '.join(validation.errors)}",
                createdAt=utc_now(),
            ),
            validation=validation,
            rollback_performed=True,
            files_written=files_written,
            error=f"Validation failed: {'; '.join(validation.errors)}",
        )

    cleanup_backup(plan.id)

    patch_kind = "constrained region" if region_name else "full-file"
    return PatchExecutionResult(
        record=PatchRecord(
            id=record_id,
            sessionId=plan.sessionId,
            planId=plan.id,
            status="applied",
            filesChanged=files_written,
            summary=f"Applied {patch_kind} patch for: {design_intent.objective[:80]}",
            createdAt=utc_now(),
        ),
        validation=validation,
        files_written=files_written,
    )


def execute_update(
    plan: PatchPlan,
    design_intent: DesignIntent,
    manifest: ProjectManifest,
    provider_client: ProviderClient,
) -> PatchExecutionResult:
    """Broad update of a target file (non-selection-based modify)."""
    record_id = f"rec-{uuid4().hex[:8]}"
    target_file = (
        plan.target.files[0] if plan.target.files
        else "preview/index.html"
    )

    if not file_exists(target_file):
        return PatchExecutionResult(
            record=PatchRecord(
                id=record_id,
                sessionId=plan.sessionId,
                planId=plan.id,
                status="failed",
                filesChanged=[],
                summary=f"Target file not found: {target_file}",
                createdAt=utc_now(),
            ),
            validation=ValidationResult(ok=False, errors=[f"File not found: {target_file}"]),
            error=f"Target file not found: {target_file}",
        )

    existing_code = read_file(target_file)
    backup_file(target_file, plan.id)
    files_written: list[str] = []

    prompt = _system_prompt_update(existing_code, design_intent)
    try:
        updated = provider_client.complete_text(prompt)
        updated = _strip_markdown_fences(updated)
    except Exception as exc:
        restore_from_backup(target_file, plan.id)
        return PatchExecutionResult(
            record=PatchRecord(
                id=record_id,
                sessionId=plan.sessionId,
                planId=plan.id,
                status="failed",
                filesChanged=[],
                summary=f"LLM update failed: {exc}",
                createdAt=utc_now(),
            ),
            validation=ValidationResult(ok=False, errors=[str(exc)]),
            error=str(exc),
        )

    write_file(target_file, updated)
    files_written.append(target_file)

    validation = validate_files(files_written)

    if not validation.ok:
        restore_from_backup(target_file, plan.id)
        return PatchExecutionResult(
            record=PatchRecord(
                id=record_id,
                sessionId=plan.sessionId,
                planId=plan.id,
                status="failed",
                filesChanged=files_written,
                summary=f"Validation failed after update: {'; '.join(validation.errors)}",
                createdAt=utc_now(),
            ),
            validation=validation,
            rollback_performed=True,
            files_written=files_written,
            error=f"Validation failed: {'; '.join(validation.errors)}",
        )

    cleanup_backup(plan.id)
    return PatchExecutionResult(
        record=PatchRecord(
            id=record_id,
            sessionId=plan.sessionId,
            planId=plan.id,
            status="applied",
            filesChanged=files_written,
            summary=f"Updated screen: {design_intent.objective[:80]}",
            createdAt=utc_now(),
        ),
        validation=validation,
        files_written=files_written,
    )


def execute_rollback(
    plan: PatchPlan,
    rollback_plan_id: str,
) -> PatchExecutionResult:
    """Restore files from a previous patch backup."""
    record_id = f"rec-{uuid4().hex[:8]}"
    restored: list[str] = []
    errors: list[str] = []

    for file_path in plan.target.files:
        if restore_from_backup(file_path, rollback_plan_id):
            restored.append(file_path)
        else:
            errors.append(f"No backup found for {file_path} from plan {rollback_plan_id}")

    status = "rolled-back" if restored and not errors else "failed"
    validation = validate_files(restored) if restored else ValidationResult()

    return PatchExecutionResult(
        record=PatchRecord(
            id=record_id,
            sessionId=plan.sessionId,
            planId=plan.id,
            status=status,
            filesChanged=restored,
            summary=f"Rolled back {len(restored)} file(s) to plan {rollback_plan_id}",
            createdAt=utc_now(),
        ),
        validation=validation,
        files_written=restored,
        error="; ".join(errors) if errors else None,
    )


def execute_patch(
    plan: PatchPlan,
    design_intent: DesignIntent,
    manifest: ProjectManifest,
    provider_client: ProviderClient,
    selected_element: Optional[SelectedElement] = None,
) -> PatchExecutionResult:
    """Route to the appropriate execution strategy."""
    if plan.strategy == "create":
        return execute_create(plan, design_intent, manifest, provider_client)
    elif plan.strategy == "targeted-update":
        return execute_targeted_update(
            plan, design_intent, manifest, selected_element, provider_client
        )
    elif plan.strategy == "update":
        return execute_update(plan, design_intent, manifest, provider_client)
    elif plan.strategy == "rollback":
        # The rollback_plan_id should be encoded in the plan steps
        rollback_id = plan.id  # fallback
        for step in plan.steps:
            if step.startswith("rollback:"):
                rollback_id = step.split(":", 1)[1].strip()
                break
        return execute_rollback(plan, rollback_id)
    else:
        return PatchExecutionResult(
            record=PatchRecord(
                id=f"rec-{uuid4().hex[:8]}",
                sessionId=plan.sessionId,
                planId=plan.id,
                status="failed",
                filesChanged=[],
                summary=f"Unknown strategy: {plan.strategy}",
                createdAt=utc_now(),
            ),
            validation=ValidationResult(ok=False, errors=[f"Unknown strategy: {plan.strategy}"]),
            error=f"Unknown strategy: {plan.strategy}",
        )
