"""Source mapper – resolves selection payloads to workspace file regions.

Given a SelectedElement (selector, componentHint, domPath, sourceHint),
this module determines:
  1. Which file contains the target
  2. Which region marker encloses it
  3. A confidence score for the mapping
  4. Fallback candidates when the mapping is ambiguous
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .file_service import file_exists, list_files, read_file
from .models import SelectedElement, SourceHint
from .patch_executor import REGION_PATTERN, extract_region


@dataclass
class MappingCandidate:
    """A possible source location for a selection."""
    file_path: str
    region_name: Optional[str]
    confidence: float  # 0.0 – 1.0
    reason: str


@dataclass
class SourceMapping:
    """Result of resolving a selection to a source location."""
    resolved: bool
    file_path: str
    region_name: Optional[str]
    confidence: float
    candidates: list[MappingCandidate] = field(default_factory=list)
    ambiguous: bool = False
    enriched_source_hint: Optional[SourceHint] = None


# ── Region index ────────────────────────────────────────────────────────

@dataclass
class RegionEntry:
    """An indexed region from a workspace file."""
    file_path: str
    name: str
    component_attr: Optional[str]
    content_preview: str  # first 200 chars of region content
    has_data_lfg_source: bool


def build_region_index(workspace_files: Optional[list[str]] = None) -> list[RegionEntry]:
    """Scan workspace HTML files and build an index of all region markers."""
    if workspace_files is None:
        workspace_files = list_files("preview")

    entries: list[RegionEntry] = []
    for fpath in workspace_files:
        if not fpath.endswith((".html", ".htm")):
            continue
        if not file_exists(fpath):
            continue
        try:
            content = read_file(fpath)
        except Exception:
            continue

        for m in REGION_PATTERN.finditer(content):
            region_name = m.group("name")
            region_content = m.group("content")

            # Check for data-lfg-component attribute
            comp_match = re.search(
                r'data-lfg-component="([^"]+)"', region_content
            )
            # Check for data-lfg-source attribute
            source_match = re.search(r'data-lfg-source="([^"]+)"', region_content)

            entries.append(RegionEntry(
                file_path=fpath,
                name=region_name,
                component_attr=comp_match.group(1) if comp_match else None,
                content_preview=region_content.strip()[:200],
                has_data_lfg_source=source_match is not None,
            ))

    return entries


# ── Mapping strategies ──────────────────────────────────────────────────

def _match_by_source_hint(
    element: SelectedElement,
    region_index: list[RegionEntry],
) -> list[MappingCandidate]:
    """Match using explicit sourceHint (highest confidence)."""
    if not element.sourceHint or not element.sourceHint.filePath:
        return []

    candidates: list[MappingCandidate] = []
    fpath = element.sourceHint.filePath

    if not file_exists(fpath):
        return []

    # If exportName is set, try to match a region by that name
    if element.sourceHint.exportName:
        for entry in region_index:
            if entry.file_path == fpath and entry.name == element.sourceHint.exportName:
                candidates.append(MappingCandidate(
                    file_path=fpath,
                    region_name=entry.name,
                    confidence=0.95,
                    reason=f"sourceHint.exportName '{entry.name}' matches region in {fpath}",
                ))
                return candidates

    # File matches but no specific region
    candidates.append(MappingCandidate(
        file_path=fpath,
        region_name=None,
        confidence=0.7,
        reason=f"sourceHint.filePath matches {fpath}",
    ))
    return candidates


def _match_by_component_hint(
    element: SelectedElement,
    region_index: list[RegionEntry],
) -> list[MappingCandidate]:
    """Match using componentHint from data-lfg-component attribute."""
    if not element.componentHint:
        return []

    candidates: list[MappingCandidate] = []
    hint = element.componentHint

    for entry in region_index:
        if entry.name == hint or entry.component_attr == hint:
            candidates.append(MappingCandidate(
                file_path=entry.file_path,
                region_name=entry.name,
                confidence=0.9,
                reason=f"componentHint '{hint}' matches region '{entry.name}' in {entry.file_path}",
            ))

    return candidates


def _match_by_selector(
    element: SelectedElement,
    region_index: list[RegionEntry],
) -> list[MappingCandidate]:
    """Match by searching selector patterns in region content."""
    if not element.selector:
        return []

    candidates: list[MappingCandidate] = []

    # Extract identifiers from the selector
    id_match = re.search(r'#([a-zA-Z0-9_-]+)', element.selector)
    class_match = re.search(r'\.([a-zA-Z0-9_-]+)', element.selector)
    attr_match = re.search(r'data-lfg-component="([^"]+)"', element.selector)

    for entry in region_index:
        score = 0.0
        reasons = []

        # data-lfg-component in selector matches region
        if attr_match and attr_match.group(1) == entry.name:
            score = 0.9
            reasons.append(f"selector attr matches region '{entry.name}'")

        # ID in selector found in region content
        if id_match:
            fpath = entry.file_path
            if file_exists(fpath):
                region_content = extract_region(read_file(fpath), entry.name) or ""
                if f'id="{id_match.group(1)}"' in region_content:
                    score = max(score, 0.8)
                    reasons.append(f"id '{id_match.group(1)}' found in region '{entry.name}'")

        # Text snippet match
        if element.textSnippet and len(element.textSnippet) > 3:
            snippet_short = element.textSnippet[:60]
            if snippet_short in entry.content_preview:
                score = max(score, 0.6)
                reasons.append(f"textSnippet found in region '{entry.name}'")

        if score > 0:
            candidates.append(MappingCandidate(
                file_path=entry.file_path,
                region_name=entry.name,
                confidence=score,
                reason="; ".join(reasons),
            ))

    return candidates


def _match_by_dom_path(
    element: SelectedElement,
    region_index: list[RegionEntry],
) -> list[MappingCandidate]:
    """Match using DOM path component hints (e.g. div[Hero])."""
    if not element.domPath:
        return []

    candidates: list[MappingCandidate] = []

    # Extract component names from DOM path entries like "div[Hero]"
    path_components = []
    for segment in element.domPath:
        bracket_match = re.search(r'\[([A-Za-z0-9_-]+)\]', segment)
        if bracket_match:
            path_components.append(bracket_match.group(1))

    if not path_components:
        return []

    for entry in region_index:
        for comp in path_components:
            if entry.name == comp or entry.component_attr == comp:
                candidates.append(MappingCandidate(
                    file_path=entry.file_path,
                    region_name=entry.name,
                    confidence=0.75,
                    reason=f"domPath component '{comp}' matches region '{entry.name}'",
                ))

    return candidates


# ── Main resolver ───────────────────────────────────────────────────────

def resolve_source(
    element: SelectedElement,
    workspace_files: Optional[list[str]] = None,
) -> SourceMapping:
    """Resolve a SelectedElement to its source file and region.

    Strategies are tried in order of confidence:
    1. Explicit sourceHint (data-lfg-source annotation)
    2. componentHint (data-lfg-component attribute)
    3. DOM path component names
    4. Selector pattern matching
    """
    region_index = build_region_index(workspace_files)

    all_candidates: list[MappingCandidate] = []

    # Try strategies in order of reliability
    for strategy in [
        _match_by_source_hint,
        _match_by_component_hint,
        _match_by_dom_path,
        _match_by_selector,
    ]:
        candidates = strategy(element, region_index)
        all_candidates.extend(candidates)

    if not all_candidates:
        # No match at all → default to entry file
        return SourceMapping(
            resolved=False,
            file_path="preview/index.html",
            region_name=None,
            confidence=0.0,
            candidates=[],
            ambiguous=False,
            enriched_source_hint=SourceHint(filePath="preview/index.html"),
        )

    # Sort by confidence descending
    all_candidates.sort(key=lambda c: c.confidence, reverse=True)

    # Deduplicate by (file, region)
    seen: set[tuple[str, Optional[str]]] = set()
    unique: list[MappingCandidate] = []
    for c in all_candidates:
        key = (c.file_path, c.region_name)
        if key not in seen:
            seen.add(key)
            unique.append(c)

    best = unique[0]

    # Determine ambiguity: multiple candidates with close confidence
    ambiguous = (
        len(unique) > 1
        and unique[1].confidence >= best.confidence - 0.15
        and unique[0].region_name != unique[1].region_name
    )

    enriched = SourceHint(
        filePath=best.file_path,
        exportName=best.region_name,
    )

    return SourceMapping(
        resolved=True,
        file_path=best.file_path,
        region_name=best.region_name,
        confidence=best.confidence,
        candidates=unique[:5],
        ambiguous=ambiguous,
        enriched_source_hint=enriched,
    )


def enrich_selected_element(element: SelectedElement) -> tuple[SelectedElement, SourceMapping]:
    """Enrich a SelectedElement with resolved source mapping.

    Returns the updated element and the mapping result.
    """
    mapping = resolve_source(element)

    # Update sourceHint with resolved mapping
    enriched = element.model_copy(update={
        "sourceHint": mapping.enriched_source_hint,
        "componentHint": element.componentHint or mapping.region_name,
    })

    return enriched, mapping
