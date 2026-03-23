"""Tests for source_mapper – selection-to-source mapping accuracy (LFG-9)."""
from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from local_figma_agent import file_service
from local_figma_agent.models import ElementBounds, SelectedElement, SourceHint
from local_figma_agent.patch_executor import _detect_region_for_selection
from local_figma_agent.source_mapper import (
    MappingCandidate,
    RegionEntry,
    SourceMapping,
    build_region_index,
    enrich_selected_element,
    resolve_source,
    _match_by_component_hint,
    _match_by_dom_path,
    _match_by_selector,
    _match_by_source_hint,
)

# ── Fixtures ────────────────────────────────────────────────────────────

SAMPLE_HTML = textwrap.dedent("""\
<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
<!-- @lfg-region:Hero -->
<div data-lfg-component="Hero">
  <h1 id="main-title">Welcome to Symphony</h1>
  <p>Build your UI with natural language</p>
</div>
<!-- @lfg-region-end:Hero -->

<!-- @lfg-region:Features -->
<div data-lfg-component="Features">
  <div class="feature-card" id="card-1">Feature 1</div>
  <div class="feature-card" id="card-2">Feature 2</div>
</div>
<!-- @lfg-region-end:Features -->

<!-- @lfg-region:Footer -->
<footer data-lfg-component="Footer">
  <p>Copyright 2026</p>
</footer>
<!-- @lfg-region-end:Footer -->
</body>
</html>
""")

OVERLAP_HTML = textwrap.dedent("""\
<!-- @lfg-region:Section1 -->
<div data-lfg-component="Section1"><p class="shared">Hello World</p></div>
<!-- @lfg-region-end:Section1 -->
<!-- @lfg-region:Section2 -->
<div data-lfg-component="Section2"><p class="shared">Hello World</p></div>
<!-- @lfg-region-end:Section2 -->
""")


def _el(**kwargs) -> SelectedElement:
    defaults = {
        "id": "sel-test",
        "sessionId": "test-session",
        "kind": "element",
        "selector": "div",
        "domPath": ["html", "body", "div"],
        "bounds": ElementBounds(x=0, y=0, width=100, height=50),
    }
    defaults.update(kwargs)
    return SelectedElement(**defaults)


@pytest.fixture(autouse=True)
def _workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point file_service to a temp workspace with sample HTML."""
    file_service._WORKSPACE_ROOT = None
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    preview = tmp_path / "preview"
    preview.mkdir()
    (preview / "index.html").write_text(SAMPLE_HTML, encoding="utf-8")
    (preview / "overlap.html").write_text(OVERLAP_HTML, encoding="utf-8")
    yield
    file_service._WORKSPACE_ROOT = None


# ── _detect_region_for_selection ────────────────────────────────────────

class TestDetectRegionForSelection:
    def test_none_element_returns_none(self):
        assert _detect_region_for_selection(SAMPLE_HTML, None) is None

    def test_matches_component_hint(self):
        assert _detect_region_for_selection(SAMPLE_HTML, _el(componentHint="Hero")) == "Hero"

    def test_matches_source_hint_export_name(self):
        el = _el(sourceHint=SourceHint(filePath="preview/index.html", exportName="Features"))
        assert _detect_region_for_selection(SAMPLE_HTML, el) == "Features"

    def test_matches_dom_path_brackets(self):
        el = _el(domPath=["html", "body", "div[Hero]", "h1#main-title"])
        assert _detect_region_for_selection(SAMPLE_HTML, el) == "Hero"

    def test_matches_selector_data_attr(self):
        el = _el(selector='[data-lfg-component="Footer"]')
        assert _detect_region_for_selection(SAMPLE_HTML, el) == "Footer"

    def test_matches_text_snippet(self):
        el = _el(selector="footer", textSnippet="Copyright 2026")
        assert _detect_region_for_selection(SAMPLE_HTML, el) == "Footer"

    def test_no_match_returns_none(self):
        el = _el(
            componentHint="Nonexistent",
            selector="div.unknown",
            domPath=["html", "body", "div"],
            textSnippet="no such text in HTML",
        )
        assert _detect_region_for_selection(SAMPLE_HTML, el) is None

    def test_source_hint_takes_priority(self):
        """sourceHint.exportName should win over componentHint."""
        el = _el(
            componentHint="Hero",
            sourceHint=SourceHint(filePath="preview/index.html", exportName="Footer"),
        )
        assert _detect_region_for_selection(SAMPLE_HTML, el) == "Footer"


# ── build_region_index ──────────────────────────────────────────────────

class TestBuildRegionIndex:
    def test_indexes_all_regions(self):
        index = build_region_index(["preview/index.html"])
        names = sorted(e.name for e in index)
        assert names == ["Features", "Footer", "Hero"]

    def test_captures_component_attr(self):
        index = build_region_index(["preview/index.html"])
        hero = next(e for e in index if e.name == "Hero")
        assert hero.component_attr == "Hero"

    def test_skips_non_html(self):
        assert build_region_index(["preview/style.css"]) == []

    def test_skips_missing_file(self):
        assert build_region_index(["preview/ghost.html"]) == []


# ── _match_by_source_hint ──────────────────────────────────────────────

class TestMatchBySourceHint:
    def test_matches_by_export_name(self):
        index = build_region_index(["preview/index.html"])
        el = _el(sourceHint=SourceHint(filePath="preview/index.html", exportName="Hero"))
        candidates = _match_by_source_hint(el, index)
        assert len(candidates) == 1
        assert candidates[0].confidence == 0.95

    def test_matches_by_file_only(self):
        index = build_region_index(["preview/index.html"])
        el = _el(sourceHint=SourceHint(filePath="preview/index.html"))
        candidates = _match_by_source_hint(el, index)
        assert len(candidates) == 1
        assert candidates[0].confidence == 0.7

    def test_no_source_hint(self):
        index = build_region_index(["preview/index.html"])
        assert _match_by_source_hint(_el(), index) == []

    def test_missing_file(self):
        index = build_region_index(["preview/index.html"])
        el = _el(sourceHint=SourceHint(filePath="preview/gone.html"))
        assert _match_by_source_hint(el, index) == []


# ── _match_by_component_hint ───────────────────────────────────────────

class TestMatchByComponentHint:
    def test_matches(self):
        index = build_region_index(["preview/index.html"])
        cs = _match_by_component_hint(_el(componentHint="Features"), index)
        assert len(cs) == 1
        assert cs[0].region_name == "Features"
        assert cs[0].confidence == 0.9

    def test_no_match(self):
        index = build_region_index(["preview/index.html"])
        assert _match_by_component_hint(_el(componentHint="Unknown"), index) == []

    def test_no_hint(self):
        index = build_region_index(["preview/index.html"])
        assert _match_by_component_hint(_el(), index) == []


# ── _match_by_dom_path ─────────────────────────────────────────────────

class TestMatchByDomPath:
    def test_matches_bracket_component(self):
        index = build_region_index(["preview/index.html"])
        cs = _match_by_dom_path(_el(domPath=["html", "body", "div[Features]", "div"]), index)
        assert len(cs) == 1
        assert cs[0].region_name == "Features"
        assert cs[0].confidence == 0.75

    def test_no_brackets(self):
        index = build_region_index(["preview/index.html"])
        assert _match_by_dom_path(_el(domPath=["html", "body", "div", "p"]), index) == []


# ── _match_by_selector ─────────────────────────────────────────────────

class TestMatchBySelector:
    def test_data_attr_selector(self):
        index = build_region_index(["preview/index.html"])
        cs = _match_by_selector(_el(selector='[data-lfg-component="Footer"]'), index)
        assert any(c.region_name == "Footer" and c.confidence == 0.9 for c in cs)

    def test_id_selector(self):
        index = build_region_index(["preview/index.html"])
        cs = _match_by_selector(_el(selector="#main-title"), index)
        assert any(c.region_name == "Hero" and c.confidence >= 0.8 for c in cs)

    def test_text_snippet_in_selector(self):
        index = build_region_index(["preview/index.html"])
        cs = _match_by_selector(_el(selector="div", textSnippet="Copyright 2026"), index)
        assert any(c.region_name == "Footer" for c in cs)


# ── resolve_source ──────────────────────────────────────────────────────

class TestResolveSource:
    def test_resolves_clear_component(self):
        m = resolve_source(_el(componentHint="Features"), ["preview/index.html"])
        assert m.resolved
        assert m.region_name == "Features"
        assert m.confidence >= 0.9
        assert not m.ambiguous

    def test_resolves_source_hint(self):
        el = _el(sourceHint=SourceHint(filePath="preview/index.html", exportName="Hero"))
        m = resolve_source(el, ["preview/index.html"])
        assert m.resolved
        assert m.region_name == "Hero"
        assert m.confidence >= 0.95

    def test_unresolvable_falls_back(self):
        el = _el(componentHint="X", selector="div.no", domPath=["html"])
        m = resolve_source(el, ["preview/index.html"])
        assert not m.resolved
        assert m.file_path == "preview/index.html"

    def test_ambiguous_detection_overlap(self):
        """Two regions with identical content → ambiguous when matched by text."""
        el = _el(selector=".shared", textSnippet="Hello World")
        m = resolve_source(el, ["preview/overlap.html"])
        assert len(m.candidates) >= 2
        assert m.ambiguous


# ── enrich_selected_element ─────────────────────────────────────────────

class TestEnrichSelectedElement:
    def test_enriches_with_source(self):
        enriched, mapping = enrich_selected_element(_el(componentHint="Hero"))
        assert enriched.sourceHint is not None
        assert enriched.sourceHint.filePath == "preview/index.html"
        assert enriched.sourceHint.exportName == "Hero"
        assert enriched.componentHint == "Hero"
        assert mapping.resolved

    def test_enriches_unknown_element(self):
        enriched, mapping = enrich_selected_element(
            _el(componentHint=None, selector="div.unknown")
        )
        # Should still set sourceHint even when unresolved
        assert enriched.sourceHint is not None
        assert enriched.sourceHint.filePath == "preview/index.html"


# ── Ambiguous fallback ──────────────────────────────────────────────────

class TestAmbiguousFallback:
    def test_clear_selection_not_ambiguous(self):
        m = resolve_source(_el(componentHint="Hero"), ["preview/index.html"])
        assert not m.ambiguous

    def test_overlap_detected(self):
        m = resolve_source(
            _el(selector=".shared", textSnippet="Hello World"),
            ["preview/overlap.html"],
        )
        assert m.ambiguous
        assert len(m.candidates) >= 2
        region_names = {c.region_name for c in m.candidates}
        assert "Section1" in region_names
        assert "Section2" in region_names
