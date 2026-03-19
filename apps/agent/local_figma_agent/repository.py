from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional
from uuid import uuid4

from psycopg import connect
from psycopg.rows import dict_row

from .models import (
    LlmProviderConfig,
    MemorySnapshot,
    ProjectFile,
    ProjectManifest,
    RuntimeHealth,
    SelectedElement,
    SessionMessage,
    SessionRecord,
    utc_now,
)


class SessionRepository:
    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or os.getenv("DATABASE_URL")

    def is_configured(self) -> bool:
        return bool(self.database_url)

    def _connect(self):
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is not configured")
        return connect(self.database_url, row_factory=dict_row)

    def ensure_session(self, session_id: str, provider: LlmProviderConfig, manifest: ProjectManifest) -> SessionRecord:
        if not self.database_url:
            return SessionRecord(id=session_id, provider=provider, manifest=manifest)

        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("select * from sessions where id = %s", (session_id,))
            row = cur.fetchone()
            if row:
                return SessionRecord(
                    id=row["id"],
                    provider=LlmProviderConfig.model_validate(row["provider"]),
                    manifest=ProjectManifest.model_validate(row["project_manifest"]),
                    summary=row.get("summary") or "",
                    latestDesignIntent=row.get("design_intent"),
                    createdAt=row["created_at"].isoformat(),
                    updatedAt=row["updated_at"].isoformat(),
                )

            cur.execute(
                """
                insert into sessions (id, provider, project_manifest, summary)
                values (%s, %s::jsonb, %s::jsonb, %s)
                """,
                (
                    session_id,
                    json.dumps(provider.model_dump(mode="json")),
                    json.dumps(manifest.model_dump(mode="json")),
                    "",
                ),
            )
            conn.commit()

        return SessionRecord(id=session_id, provider=provider, manifest=manifest)

    def load_memory(self, session_id: str) -> MemorySnapshot:
        if not self.database_url:
            return MemorySnapshot(summary="")

        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("select summary from sessions where id = %s", (session_id,))
            session_row = cur.fetchone()
            cur.execute(
                """
                select id, session_id, role, body, selected_element, created_at
                from messages
                where session_id = %s
                order by created_at asc
                """,
                (session_id,),
            )
            rows = cur.fetchall()

        messages: list[SessionMessage] = []
        selected_elements: list[SelectedElement] = []
        for row in rows:
            selected = row.get("selected_element")
            if selected:
                selected_elements.append(SelectedElement.model_validate(selected))
            messages.append(
                SessionMessage(
                    id=row["id"],
                    sessionId=row["session_id"],
                    role=row["role"],
                    parts=row["body"],
                    selectedElementId=selected.get("id") if selected else None,
                    createdAt=row["created_at"].isoformat(),
                )
            )

        return MemorySnapshot(
            summary=(session_row or {}).get("summary") or "",
            selectedElements=selected_elements,
            messages=messages,
        )

    def append_message(self, message: SessionMessage, selected_element: Optional[SelectedElement] = None) -> None:
        if not self.database_url:
            return

        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                insert into messages (id, session_id, role, body, selected_element, created_at)
                values (%s, %s, %s, %s::jsonb, %s::jsonb, now())
                """,
                (
                    message.id,
                    message.sessionId,
                    message.role,
                    json.dumps([part.model_dump(mode="json") for part in message.parts]),
                    json.dumps(selected_element.model_dump(mode="json")) if selected_element else None,
                ),
            )
            conn.commit()

    def update_summary(self, session_id: str, summary: str, design_intent: dict) -> None:
        if not self.database_url:
            return

        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                update sessions
                set summary = %s,
                    design_intent = %s::jsonb,
                    updated_at = now()
                where id = %s
                """,
                (summary, json.dumps(design_intent), session_id),
            )
            conn.commit()


def build_project_manifest(workspace_root: Optional[str] = None) -> ProjectManifest:
    configured_root = Path(workspace_root or os.getenv("WORKSPACE_ROOT", "/app/workspace"))
    if configured_root.exists():
        root = configured_root.resolve()
    else:
        root = (Path(__file__).resolve().parents[3] / "workspace").resolve()
    preview_root = root / "preview"
    files: list[ProjectFile] = []

    if preview_root.exists():
        for path in sorted(preview_root.rglob("*")):
            if not path.is_file():
                continue
            relative_path = str(path.relative_to(root))
            kind = "asset"
            if path.suffix in {".tsx", ".jsx", ".js"}:
                kind = "component"
            elif path.suffix == ".html":
                kind = "route"
            elif path.suffix == ".css":
                kind = "style"
            files.append(
                ProjectFile(
                    path=relative_path,
                    kind=kind,
                    entry=relative_path == "preview/index.html",
                )
            )

    return ProjectManifest(
        projectId=os.getenv("PROJECT_NAME", "local-figma"),
        name=os.getenv("PROJECT_NAME", "local-figma"),
        framework="react",
        runtimePackageManager="pnpm",
        workspaceRoot=str(root),
        runtimeEntry="preview/index.html",
        files=files,
    )


def default_runtime_status() -> RuntimeHealth:
    runtime_url = os.getenv("RUNTIME_PUBLIC_URL", f"http://localhost:{os.getenv('RUNTIME_PORT', '3001')}")
    return RuntimeHealth(
        projectId=os.getenv("PROJECT_NAME", "local-figma"),
        status="ready",
        runtimeUrl=runtime_url,
        buildId=f"build-{uuid4().hex[:8]}",
        lastHeartbeatAt=utc_now(),
    )
