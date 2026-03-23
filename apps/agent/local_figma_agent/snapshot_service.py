"""Snapshot service – create / list / restore workspace snapshots.

A snapshot captures all files under workspace/preview as a tar.gz archive
and stores it alongside metadata in the ``snapshots`` Postgres table.
Restoring a snapshot replaces the current workspace/preview contents.
"""
from __future__ import annotations

import io
import tarfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .file_service import workspace_root, list_files


def _snapshot_id() -> str:
    return f"snap-{uuid.uuid4().hex[:8]}"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── archive helpers ─────────────────────────────────────────────────────────

def create_workspace_archive() -> tuple[bytes, list[str]]:
    """Tar-gz all files under ``preview/`` and return (archive_bytes, file_list)."""
    root = workspace_root()
    preview = root / "preview"
    buf = io.BytesIO()
    file_list: list[str] = []

    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        if preview.is_dir():
            for path in sorted(preview.rglob("*")):
                if not path.is_file():
                    continue
                rel = str(path.relative_to(root))
                tar.add(str(path), arcname=rel)
                file_list.append(rel)

    return buf.getvalue(), file_list


def restore_workspace_archive(archive_bytes: bytes) -> list[str]:
    """Replace workspace/preview with files from *archive_bytes*.

    Returns the list of files extracted.
    """
    root = workspace_root()
    preview = root / "preview"

    # Clear current preview directory
    if preview.is_dir():
        import shutil
        shutil.rmtree(preview)
    preview.mkdir(parents=True, exist_ok=True)

    buf = io.BytesIO(archive_bytes)
    extracted: list[str] = []
    with tarfile.open(fileobj=buf, mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            # Security: prevent path traversal in archive
            resolved = (root / member.name).resolve()
            if not str(resolved).startswith(str(root)):
                continue
            tar.extract(member, path=str(root))
            extracted.append(member.name)

    return sorted(extracted)


# ── persistence bridge ──────────────────────────────────────────────────────

def create_snapshot(
    repo: Any,
    session_id: str,
    label: str = "",
    patch_record_id: str | None = None,
) -> dict[str, Any]:
    """Create a snapshot of the current workspace and persist it."""
    archive, file_list = create_workspace_archive()
    snapshot_id = _snapshot_id()

    repo.create_snapshot(
        snapshot_id=snapshot_id,
        session_id=session_id,
        label=label,
        archive=archive,
        file_list=file_list,
        patch_record_id=patch_record_id,
    )

    return {
        "id": snapshot_id,
        "sessionId": session_id,
        "label": label,
        "fileCount": len(file_list),
        "files": file_list,
        "patchRecordId": patch_record_id,
        "createdAt": _utc_now_iso(),
    }


def restore_snapshot(repo: Any, snapshot_id: str) -> dict[str, Any]:
    """Restore a snapshot by ID – replaces current workspace/preview."""
    row = repo.get_snapshot(snapshot_id)
    extracted = restore_workspace_archive(row["archive"])
    return {
        "id": row["id"],
        "sessionId": row["sessionId"],
        "label": row["label"],
        "restoredFiles": extracted,
    }


def list_snapshots(repo: Any, session_id: str) -> list[dict[str, Any]]:
    """List snapshots for a session (without archive blobs)."""
    return repo.list_snapshots(session_id)
