"""Workspace file read/write service.

Operates on the shared workspace volume mounted at WORKSPACE_ROOT.
Both the agent and runtime containers see the same directory.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional


_WORKSPACE_ROOT: Optional[Path] = None


def workspace_root() -> Path:
    global _WORKSPACE_ROOT
    if _WORKSPACE_ROOT is not None:
        return _WORKSPACE_ROOT
    configured = os.getenv("WORKSPACE_ROOT", "/app/workspace")
    root = Path(configured)
    if not root.exists():
        root = Path(__file__).resolve().parents[3] / "workspace"
    _WORKSPACE_ROOT = root.resolve()
    return _WORKSPACE_ROOT


def _safe_resolve(relative: str) -> Path:
    """Resolve *relative* inside workspace root, preventing path traversal."""
    root = workspace_root()
    resolved = (root / relative).resolve()
    if not str(resolved).startswith(str(root)):
        raise ValueError(f"Path traversal blocked: {relative}")
    return resolved


# ── read ────────────────────────────────────────────────────────────────────

def read_file(relative_path: str) -> str:
    """Return UTF-8 content of a file inside the workspace."""
    target = _safe_resolve(relative_path)
    if not target.is_file():
        raise FileNotFoundError(f"File not found: {relative_path}")
    return target.read_text(encoding="utf-8")


def file_exists(relative_path: str) -> bool:
    return _safe_resolve(relative_path).is_file()


def list_files(relative_dir: str = "") -> list[str]:
    """List files under *relative_dir* recursively, returning workspace-relative paths."""
    root = workspace_root()
    base = _safe_resolve(relative_dir)
    if not base.is_dir():
        return []
    return sorted(
        str(p.relative_to(root))
        for p in base.rglob("*")
        if p.is_file()
    )


# ── write ───────────────────────────────────────────────────────────────────

def write_file(relative_path: str, content: str) -> Path:
    """Write *content* to a workspace file.  Creates parent directories."""
    target = _safe_resolve(relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def delete_file(relative_path: str) -> bool:
    target = _safe_resolve(relative_path)
    if target.is_file():
        target.unlink()
        return True
    return False


# ── backup / rollback ──────────────────────────────────────────────────────

_BACKUP_DIR = ".lfg-backups"


def backup_file(relative_path: str, patch_id: str) -> Optional[str]:
    """Copy the current file to a backup location.  Returns backup relative path or None."""
    target = _safe_resolve(relative_path)
    if not target.is_file():
        return None
    backup_relative = f"{_BACKUP_DIR}/{patch_id}/{relative_path}"
    backup_path = _safe_resolve(backup_relative)
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, backup_path)
    return backup_relative


def restore_from_backup(relative_path: str, patch_id: str) -> bool:
    """Restore a file from its backup.  Returns True on success."""
    backup_relative = f"{_BACKUP_DIR}/{patch_id}/{relative_path}"
    backup_path = _safe_resolve(backup_relative)
    if not backup_path.is_file():
        return False
    target = _safe_resolve(relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup_path, target)
    return True


def cleanup_backup(patch_id: str) -> None:
    backup_dir = _safe_resolve(f"{_BACKUP_DIR}/{patch_id}")
    if backup_dir.is_dir():
        shutil.rmtree(backup_dir)
