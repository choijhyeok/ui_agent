from __future__ import annotations

import json
import os
import uuid
from typing import Any

import psycopg


class PersistenceError(Exception):
    pass


class NotFoundError(PersistenceError):
    pass


class BadRequestError(PersistenceError):
    pass


def _decode_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


class PostgresRepository:
    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.getenv("DATABASE_URL", "")
        if not self.database_url:
            raise BadRequestError("DATABASE_URL is required")

    def _connect(self):
        return psycopg.connect(self.database_url)

    def ping(self) -> bool:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select 1")
                return cursor.fetchone()[0] == 1

    def create_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = payload.get("id") or f"session-{uuid.uuid4().hex}"
        provider = payload.get("provider")
        manifest = payload.get("manifest")
        if not provider or not manifest:
            raise BadRequestError("provider and manifest are required")

        design_intent = payload.get("latestDesignIntent")
        summary = payload.get("summary")

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into sessions (id, provider, design_intent, project_manifest, summary)
                    values (%s, %s::jsonb, %s::jsonb, %s::jsonb, %s)
                    """,
                    (
                        session_id,
                        json.dumps(provider),
                        json.dumps(design_intent) if design_intent is not None else None,
                        json.dumps(manifest),
                        summary,
                    ),
                )
            connection.commit()

        if summary is not None or payload.get("structuredMemory") is not None:
            self.upsert_memory(
                session_id,
                {
                    "summary": summary or "",
                    "structuredMemory": payload.get("structuredMemory") or {},
                },
            )

        return self.get_session(session_id)

    def get_session(self, session_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select
                      s.id,
                      s.provider,
                      s.design_intent,
                      s.project_manifest,
                      coalesce(sm.summary, s.summary) as summary,
                      s.created_at,
                      s.updated_at
                    from sessions s
                    left join session_memory sm on sm.session_id = s.id
                    where s.id = %s
                    """,
                    (session_id,),
                )
                row = cursor.fetchone()

        if row is None:
            raise NotFoundError(f"session {session_id} not found")

        return {
            "id": row[0],
            "provider": _decode_json(row[1]),
            "latestDesignIntent": _decode_json(row[2]),
            "manifest": _decode_json(row[3]),
            "summary": row[4],
            "createdAt": row[5].isoformat(),
            "updatedAt": row[6].isoformat(),
        }

    def create_message(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        message_id = payload.get("id") or f"message-{uuid.uuid4().hex}"
        role = payload.get("role")
        parts = payload.get("parts")
        if not role or parts is None:
            raise BadRequestError("role and parts are required")

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into messages (id, session_id, role, body, selected_element_id)
                    values (%s, %s, %s, %s::jsonb, %s)
                    returning created_at
                    """,
                    (
                        message_id,
                        session_id,
                        role,
                        json.dumps({"parts": parts}),
                        payload.get("selectedElementId"),
                    ),
                )
                created_at = cursor.fetchone()[0]
            connection.commit()

        return {
            "id": message_id,
            "sessionId": session_id,
            "role": role,
            "parts": parts,
            "selectedElementId": payload.get("selectedElementId"),
            "createdAt": created_at.isoformat(),
        }

    def list_messages(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select id, role, body, selected_element_id, created_at
                    from messages
                    where session_id = %s
                    order by created_at asc, id asc
                    """,
                    (session_id,),
                )
                rows = cursor.fetchall()

        return [
            {
                "id": row[0],
                "sessionId": session_id,
                "role": row[1],
                "parts": (_decode_json(row[2]) or {}).get("parts", []),
                "selectedElementId": row[3],
                "createdAt": row[4].isoformat(),
            }
            for row in rows
        ]

    def upsert_memory(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        summary = payload.get("summary", "")
        structured_memory = payload.get("structuredMemory") or {}

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into session_memory (session_id, summary, structured_memory)
                    values (%s, %s, %s::jsonb)
                    on conflict (session_id) do update
                    set
                      summary = excluded.summary,
                      structured_memory = excluded.structured_memory,
                      updated_at = now()
                    returning created_at, updated_at
                    """,
                    (session_id, summary, json.dumps(structured_memory)),
                )
                created_at, updated_at = cursor.fetchone()
                cursor.execute(
                    """
                    update sessions
                    set summary = %s, updated_at = now()
                    where id = %s
                    """,
                    (summary, session_id),
                )
            connection.commit()

        return {
            "sessionId": session_id,
            "summary": summary,
            "structuredMemory": structured_memory,
            "createdAt": created_at.isoformat(),
            "updatedAt": updated_at.isoformat(),
        }

    def get_memory(self, session_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select summary, structured_memory, created_at, updated_at
                    from session_memory
                    where session_id = %s
                    """,
                    (session_id,),
                )
                row = cursor.fetchone()

        if row is None:
            return {
                "sessionId": session_id,
                "summary": "",
                "structuredMemory": {},
                "createdAt": None,
                "updatedAt": None,
            }

        return {
            "sessionId": session_id,
            "summary": row[0],
            "structuredMemory": _decode_json(row[1]) or {},
            "createdAt": row[2].isoformat(),
            "updatedAt": row[3].isoformat(),
        }

    def create_selected_element(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        element_id = payload.get("id") or f"selection-{uuid.uuid4().hex}"
        kind = payload.get("kind")
        selector = payload.get("selector")
        dom_path = payload.get("domPath")
        bounds = payload.get("bounds")
        captured_at = payload.get("capturedAt")
        if not kind or not selector or dom_path is None or bounds is None or captured_at is None:
            raise BadRequestError("kind, selector, domPath, bounds, and capturedAt are required")

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into selected_elements (
                      id,
                      session_id,
                      kind,
                      selector,
                      dom_path,
                      text_snippet,
                      bounds,
                      note,
                      component_hint,
                      source_hint,
                      captured_at
                    )
                    values (%s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s, %s, %s::jsonb, %s)
                    """,
                    (
                        element_id,
                        session_id,
                        kind,
                        selector,
                        json.dumps(dom_path),
                        payload.get("textSnippet"),
                        json.dumps(bounds),
                        payload.get("note"),
                        payload.get("componentHint"),
                        json.dumps(payload.get("sourceHint")) if payload.get("sourceHint") is not None else None,
                        captured_at,
                    ),
                )
            connection.commit()

        return {
            "id": element_id,
            "sessionId": session_id,
            "kind": kind,
            "selector": selector,
            "domPath": dom_path,
            "textSnippet": payload.get("textSnippet"),
            "bounds": bounds,
            "note": payload.get("note"),
            "componentHint": payload.get("componentHint"),
            "sourceHint": payload.get("sourceHint"),
            "capturedAt": captured_at,
        }

    def list_selected_elements(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select id, kind, selector, dom_path, text_snippet, bounds, note, component_hint, source_hint, captured_at
                    from selected_elements
                    where session_id = %s
                    order by captured_at asc, id asc
                    """,
                    (session_id,),
                )
                rows = cursor.fetchall()

        return [
            {
                "id": row[0],
                "sessionId": session_id,
                "kind": row[1],
                "selector": row[2],
                "domPath": _decode_json(row[3]) or [],
                "textSnippet": row[4],
                "bounds": _decode_json(row[5]) or {},
                "note": row[6],
                "componentHint": row[7],
                "sourceHint": _decode_json(row[8]),
                "capturedAt": row[9].isoformat(),
            }
            for row in rows
        ]

    def create_patch_record(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        record_id = payload.get("id") or f"patch-{uuid.uuid4().hex}"
        plan = payload.get("patchPlan")
        status = payload.get("status")
        files_changed = payload.get("filesChanged")
        summary = payload.get("summary")
        if plan is None or not status or files_changed is None or summary is None:
            raise BadRequestError("patchPlan, status, filesChanged, and summary are required")

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into patch_records (
                      id,
                      session_id,
                      patch_plan,
                      plan_id,
                      status,
                      files_changed,
                      summary,
                      files
                    )
                    values (%s, %s, %s::jsonb, %s, %s, %s::jsonb, %s, %s::jsonb)
                    returning created_at
                    """,
                    (
                        record_id,
                        session_id,
                        json.dumps(plan),
                        plan.get("id"),
                        status,
                        json.dumps(files_changed),
                        summary,
                        json.dumps(files_changed),
                    ),
                )
                created_at = cursor.fetchone()[0]
            connection.commit()

        return {
            "id": record_id,
            "sessionId": session_id,
            "planId": plan.get("id"),
            "status": status,
            "filesChanged": files_changed,
            "summary": summary,
            "createdAt": created_at.isoformat(),
        }

    def list_patch_records(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select id, coalesce(plan_id, patch_plan->>'id'), status, coalesce(files_changed, files), summary, created_at
                    from patch_records
                    where session_id = %s
                    order by created_at asc, id asc
                    """,
                    (session_id,),
                )
                rows = cursor.fetchall()

        return [
            {
                "id": row[0],
                "sessionId": session_id,
                "planId": row[1],
                "status": row[2],
                "filesChanged": _decode_json(row[3]) or [],
                "summary": row[4] or "",
                "createdAt": row[5].isoformat(),
            }
            for row in rows
        ]

    def restore_session(self, session_id: str) -> dict[str, Any]:
        return {
            "session": self.get_session(session_id),
            "memory": self.get_memory(session_id),
            "messages": self.list_messages(session_id),
            "selectedElements": self.list_selected_elements(session_id),
            "patchRecords": self.list_patch_records(session_id),
        }
