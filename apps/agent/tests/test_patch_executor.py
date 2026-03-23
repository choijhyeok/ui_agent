"""Tests for the patch engine – file service, build validation, and patch execution."""
from __future__ import annotations

import os
import shutil
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from local_figma_agent import file_service
from local_figma_agent.build_validator import (
    ValidationResult,
    validate_entry_point,
    validate_files,
    validate_html,
    validate_js,
)
from local_figma_agent.models import (
    DesignIntent,
    ElementBounds,
    LayoutIntent,
    PatchPlan,
    PatchTarget,
    ProjectManifest,
    SelectedElement,
    SourceHint,
)
from local_figma_agent.patch_executor import (
    REGION_PATTERN,
    execute_create,
    execute_patch,
    execute_targeted_update,
    execute_update,
    extract_region,
    inject_markers,
    replace_region,
)


@pytest.fixture(autouse=True)
def _workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Create a temporary workspace and point file_service at it."""
    # Reset cached root
    file_service._WORKSPACE_ROOT = None
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    # Create preview directory with a basic index.html
    preview = tmp_path / "preview"
    preview.mkdir()
    (preview / "index.html").write_text(
        textwrap.dedent("""\
        <!doctype html>
        <html lang="en">
        <head><meta charset="utf-8"><title>Test</title></head>
        <body>
        <!-- @lfg-region:Header -->
        <header data-lfg-component="Header"><h1>Hello</h1></header>
        <!-- @lfg-region-end:Header -->
        <!-- @lfg-region:Content -->
        <main data-lfg-component="Content"><p>World</p></main>
        <!-- @lfg-region-end:Content -->
        </body>
        </html>
        """),
        encoding="utf-8",
    )
    yield
    file_service._WORKSPACE_ROOT = None


# ── file_service tests ──────────────────────────────────────────────────

class TestFileService:
    def test_read_file(self):
        content = file_service.read_file("preview/index.html")
        assert "<h1>Hello</h1>" in content

    def test_write_and_read(self):
        file_service.write_file("preview/new.html", "<p>New</p>")
        assert file_service.file_exists("preview/new.html")
        assert file_service.read_file("preview/new.html") == "<p>New</p>"

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            file_service.read_file("preview/does-not-exist.html")

    def test_list_files(self):
        files = file_service.list_files("preview")
        assert "preview/index.html" in files

    def test_backup_and_restore(self):
        original = file_service.read_file("preview/index.html")
        file_service.backup_file("preview/index.html", "plan-test-1")
        file_service.write_file("preview/index.html", "<h1>Changed</h1>")
        assert file_service.read_file("preview/index.html") == "<h1>Changed</h1>"
        assert file_service.restore_from_backup("preview/index.html", "plan-test-1")
        assert file_service.read_file("preview/index.html") == original

    def test_delete_file(self):
        file_service.write_file("preview/temp.html", "temp")
        assert file_service.delete_file("preview/temp.html")
        assert not file_service.file_exists("preview/temp.html")

    def test_path_traversal_blocked(self):
        with pytest.raises(ValueError, match="Path traversal"):
            file_service.read_file("../../etc/passwd")


# ── marker tests ─────────────────────────────────────────────────────────

class TestMarkers:
    def test_inject_markers(self):
        html = "<div>Test</div>"
        result = inject_markers(html, "TestComponent")
        assert "<!-- @lfg-region:TestComponent -->" in result
        assert "<!-- @lfg-region-end:TestComponent -->" in result

    def test_inject_markers_idempotent(self):
        html = "<!-- @lfg-region:X --><div>Test</div><!-- @lfg-region-end:X -->"
        assert inject_markers(html, "X") == html

    def test_extract_region(self):
        content = file_service.read_file("preview/index.html")
        region = extract_region(content, "Header")
        assert region is not None
        assert "<h1>Hello</h1>" in region

    def test_extract_region_missing(self):
        content = file_service.read_file("preview/index.html")
        assert extract_region(content, "NonExistent") is None

    def test_replace_region(self):
        content = file_service.read_file("preview/index.html")
        new_content = replace_region(content, "Header", '<header data-lfg-component="Header"><h1>Updated</h1></header>')
        assert "<h1>Updated</h1>" in new_content
        assert "<h1>Hello</h1>" not in new_content
        # Content region should be unchanged
        assert "<p>World</p>" in new_content


# ── build_validator tests ────────────────────────────────────────────────

class TestBuildValidator:
    def test_valid_html(self):
        result = validate_html("<html><body><p>Test</p></body></html>", "test.html")
        assert result.ok

    def test_valid_js(self):
        result = validate_js("function foo() { return 1; }", "test.js")
        assert result.ok

    def test_unbalanced_js(self):
        result = validate_js("function foo() {{{{{ return 1; }", "test.js")
        assert not result.ok

    def test_entry_point_valid(self):
        result = validate_entry_point()
        assert result.ok

    def test_entry_point_missing(self):
        file_service.delete_file("preview/index.html")
        result = validate_entry_point()
        assert not result.ok

    def test_validate_files(self):
        result = validate_files(["preview/index.html"])
        assert result.ok


# ── patch_executor tests ─────────────────────────────────────────────────

def _make_plan(strategy: str = "create", session_id: str = "sess-1", files: list[str] | None = None) -> PatchPlan:
    return PatchPlan(
        id="plan-test-001",
        sessionId=session_id,
        strategy=strategy,
        target=PatchTarget(
            intentSummary="Test patch",
            files=files or [],
        ),
        steps=["Step 1"],
        validation=["Check 1"],
    )


def _make_design_intent(objective: str = "Create a dashboard") -> DesignIntent:
    return DesignIntent(
        objective=objective,
        screenType="dashboard",
        layout=LayoutIntent(direction="column", density="comfortable", regions=["header", "content"]),
        tone=["professional"],
        styleReferences=[],
        lockedConstraints=[],
    )


def _make_manifest() -> ProjectManifest:
    return ProjectManifest(
        projectId="test",
        name="test",
        framework="react",
        runtimePackageManager="pnpm",
        workspaceRoot=str(file_service.workspace_root()),
        runtimeEntry="preview/index.html",
        files=[],
    )


def _make_selected_element(component_hint: str = "Header") -> SelectedElement:
    return SelectedElement(
        id="sel-1",
        sessionId="sess-1",
        kind="element",
        selector="header",
        domPath=["html", "body", "header"],
        textSnippet="Hello",
        bounds=ElementBounds(x=0, y=0, width=100, height=50),
        componentHint=component_hint,
        sourceHint=SourceHint(filePath="preview/index.html"),
    )


class TestExecuteCreate:
    def test_success(self):
        mock_provider = MagicMock()
        mock_provider.complete_text.return_value = textwrap.dedent("""\
        <!doctype html>
        <html lang="en">
        <head><meta charset="utf-8"><title>Dashboard</title></head>
        <body>
        <!-- @lfg-region:Dashboard -->
        <div data-lfg-component="Dashboard"><h1>Dashboard</h1></div>
        <!-- @lfg-region-end:Dashboard -->
        </body>
        </html>
        """)

        result = execute_create(_make_plan(), _make_design_intent(), _make_manifest(), mock_provider)
        assert result.record.status == "applied"
        assert "preview/index.html" in result.files_written
        # Verify file was actually written
        content = file_service.read_file("preview/index.html")
        assert "Dashboard" in content

    def test_llm_failure_restores_backup(self):
        original = file_service.read_file("preview/index.html")
        mock_provider = MagicMock()
        mock_provider.complete_text.side_effect = RuntimeError("LLM down")

        result = execute_create(_make_plan(), _make_design_intent(), _make_manifest(), mock_provider)
        assert result.record.status == "failed"
        assert result.error is not None
        # Original should be preserved
        assert file_service.read_file("preview/index.html") == original


class TestExecuteTargetedUpdate:
    def test_constrained_region_patch(self):
        mock_provider = MagicMock()
        mock_provider.complete_text.return_value = (
            '<header data-lfg-component="Header"><h1>Updated Title</h1></header>'
        )

        plan = _make_plan(strategy="targeted-update", files=["preview/index.html"])
        selected = _make_selected_element("Header")
        result = execute_targeted_update(
            plan, _make_design_intent("Change header title"), _make_manifest(), selected, mock_provider
        )
        assert result.record.status == "applied"
        content = file_service.read_file("preview/index.html")
        assert "Updated Title" in content
        # Content region should be untouched
        assert "<p>World</p>" in content

    def test_file_not_found(self):
        mock_provider = MagicMock()
        plan = _make_plan(strategy="targeted-update", files=["preview/nonexistent.html"])
        result = execute_targeted_update(
            plan, _make_design_intent(), _make_manifest(), None, mock_provider
        )
        assert result.record.status == "failed"
        assert "not found" in result.error


class TestExecuteUpdate:
    def test_success(self):
        mock_provider = MagicMock()
        mock_provider.complete_text.return_value = textwrap.dedent("""\
        <!doctype html>
        <html lang="en">
        <head><meta charset="utf-8"><title>Updated</title></head>
        <body>
        <!-- @lfg-region:Header -->
        <header data-lfg-component="Header"><h1>Modified</h1></header>
        <!-- @lfg-region-end:Header -->
        <!-- @lfg-region:Content -->
        <main data-lfg-component="Content"><p>New content</p></main>
        <!-- @lfg-region-end:Content -->
        </body>
        </html>
        """)

        plan = _make_plan(strategy="update", files=["preview/index.html"])
        result = execute_update(plan, _make_design_intent("Update content"), _make_manifest(), mock_provider)
        assert result.record.status == "applied"
        content = file_service.read_file("preview/index.html")
        assert "Modified" in content


class TestExecutePatchRouter:
    def test_routes_to_create(self):
        mock_provider = MagicMock()
        mock_provider.complete_text.return_value = textwrap.dedent("""\
        <!doctype html>
        <html><head><meta charset="utf-8"><title>New</title></head>
        <body><div>Created</div></body></html>
        """)

        plan = _make_plan(strategy="create")
        result = execute_patch(plan, _make_design_intent(), _make_manifest(), mock_provider)
        assert result.record.status == "applied"

    def test_routes_to_targeted(self):
        mock_provider = MagicMock()
        mock_provider.complete_text.return_value = (
            '<header data-lfg-component="Header"><h1>Targeted</h1></header>'
        )

        plan = _make_plan(strategy="targeted-update", files=["preview/index.html"])
        selected = _make_selected_element("Header")
        result = execute_patch(plan, _make_design_intent(), _make_manifest(), mock_provider, selected)
        assert result.record.status == "applied"

    def test_unknown_strategy_rejected_by_model(self):
        """PatchPlan.strategy is a Literal type – invalid values are rejected at construction."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="literal_error"):
            _make_plan(strategy="unknown")
