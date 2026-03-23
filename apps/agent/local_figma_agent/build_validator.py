"""Build validation for generated/patched workspace files.

Since the runtime serves static HTML/CSS/JS (no bundler), validation checks:
 - HTML structure is parseable
 - Referenced local assets exist
 - Entry point still resolves
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Optional

from . import file_service


@dataclass
class ValidationResult:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        self.errors.append(message)
        self.ok = False

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)


class _StructureChecker(HTMLParser):
    """Lightweight check that HTML can be parsed without fatal errors."""

    def __init__(self) -> None:
        super().__init__()
        self.parse_error: Optional[str] = None
        self._stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        void_elements = {
            "area", "base", "br", "col", "embed", "hr", "img",
            "input", "link", "meta", "source", "track", "wbr",
        }
        if tag.lower() not in void_elements:
            self._stack.append(tag.lower())

    def handle_endtag(self, tag: str) -> None:
        if self._stack and self._stack[-1] == tag.lower():
            self._stack.pop()

    def error(self, message: str) -> None:  # type: ignore[override]
        self.parse_error = message


def validate_html(content: str, relative_path: str) -> ValidationResult:
    result = ValidationResult()
    checker = _StructureChecker()
    try:
        checker.feed(content)
    except Exception as exc:
        result.add_error(f"{relative_path}: HTML parse error – {exc}")
        return result

    if checker.parse_error:
        result.add_error(f"{relative_path}: {checker.parse_error}")

    # Check local asset references
    src_pattern = re.compile(r'(?:src|href)\s*=\s*["\'](?!https?://|//|#|data:)([^"\']+)["\']', re.IGNORECASE)
    for match in src_pattern.finditer(content):
        ref = match.group(1)
        if ref.startswith("/"):
            ref = ref.lstrip("/")
        else:
            import posixpath
            ref = posixpath.normpath(posixpath.join(posixpath.dirname(relative_path), ref))
        if not file_service.file_exists(ref):
            result.add_warning(f"{relative_path}: referenced asset not found – {match.group(1)}")

    return result


def validate_js(content: str, relative_path: str) -> ValidationResult:
    """Basic JS validation – check for obvious syntax issues."""
    result = ValidationResult()
    open_braces = content.count("{") - content.count("}")
    open_parens = content.count("(") - content.count(")")
    open_brackets = content.count("[") - content.count("]")

    if abs(open_braces) > 2:
        result.add_error(f"{relative_path}: unbalanced braces (delta={open_braces})")
    if abs(open_parens) > 2:
        result.add_error(f"{relative_path}: unbalanced parentheses (delta={open_parens})")
    if abs(open_brackets) > 2:
        result.add_error(f"{relative_path}: unbalanced brackets (delta={open_brackets})")

    return result


def validate_entry_point() -> ValidationResult:
    """Verify the preview entry point exists and is valid HTML."""
    result = ValidationResult()
    entry = "preview/index.html"
    if not file_service.file_exists(entry):
        result.add_error(f"Entry point missing: {entry}")
        return result

    content = file_service.read_file(entry)
    html_result = validate_html(content, entry)
    result.errors.extend(html_result.errors)
    result.warnings.extend(html_result.warnings)
    if html_result.errors:
        result.ok = False
    return result


def validate_files(relative_paths: list[str]) -> ValidationResult:
    """Run validation on a set of workspace files."""
    combined = ValidationResult()

    for path in relative_paths:
        if not file_service.file_exists(path):
            combined.add_warning(f"File not found for validation: {path}")
            continue

        content = file_service.read_file(path)

        if path.endswith(".html"):
            sub = validate_html(content, path)
        elif path.endswith((".js", ".jsx", ".mjs")):
            sub = validate_js(content, path)
        elif path.endswith(".css"):
            sub = ValidationResult()  # CSS validation is lightweight
        else:
            sub = ValidationResult()

        combined.errors.extend(sub.errors)
        combined.warnings.extend(sub.warnings)
        if not sub.ok:
            combined.ok = False

    # Always check entry point
    entry = validate_entry_point()
    combined.errors.extend(entry.errors)
    combined.warnings.extend(entry.warnings)
    if not entry.ok:
        combined.ok = False

    return combined
