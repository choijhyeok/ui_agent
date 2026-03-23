from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .models import OrchestrationRequest, OrchestrationResponse, PatchPlan, DesignIntent
from .orchestrator import AgentOrchestrator
from .patch_executor import execute_patch as run_patch
from .providers import build_provider_client, load_provider_config
from .repository import SessionRepository, build_project_manifest
from persistence import BadRequestError, NotFoundError, PersistenceError, PostgresRepository
from service import PersistenceService


def create_app() -> FastAPI:
    app = FastAPI(title="Local Figma Agent", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    provider_config = load_provider_config()
    repository = SessionRepository()
    provider_client = build_provider_client(provider_config)
    orchestrator = AgentOrchestrator(repository, provider_client, provider_config)
    persistence_repository = PostgresRepository(os.getenv("DATABASE_URL")) if os.getenv("DATABASE_URL") else None
    persistence_service = PersistenceService(persistence_repository) if persistence_repository else None

    @app.get("/health")
    def health() -> dict:
        database_ready = False
        if persistence_service is not None:
            database_ready = persistence_service.health()["databaseReady"]
        return {
            "status": "ok" if database_ready or not repository.is_configured() else "degraded",
            "provider": provider_config.model_dump(mode="json"),
            "databaseUrlConfigured": repository.is_configured(),
            "databaseReady": database_ready,
            "langgraph": "ready",
        }

    @app.post("/orchestrate", response_model=OrchestrationResponse)
    def orchestrate(request: OrchestrationRequest) -> OrchestrationResponse:
        state = orchestrator.run(request)
        return OrchestrationResponse(
            sessionId=request.sessionId,
            intentKind=state["intentKind"],
            designIntent=state["designIntent"],
            manifest=state["manifest"],
            patchPlan=state["patchPlan"],
            patchRecord=state.get("patchRecord"),
            patchValidation=state.get("patchValidation"),
            filesWritten=state.get("filesWritten", []),
            memory=state["memory"],
            runtimeStatus=state["runtimeStatus"],
            response=state["response"],
            provider=provider_config,
        )

    @app.post("/provider/smoke")
    def provider_smoke() -> dict:
        result = provider_client.smoke()
        return result.model_dump(mode="json")

    @app.post("/execute-patch")
    def execute_patch_endpoint(payload: dict) -> dict:
        """Standalone patch execution – accepts a PatchPlan + DesignIntent and executes it."""
        try:
            plan = PatchPlan.model_validate(payload["patchPlan"])
            design_intent = DesignIntent.model_validate(payload["designIntent"])
        except (KeyError, Exception) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid payload: {exc}") from exc

        manifest = build_project_manifest()
        selected_element = None
        if payload.get("selectedElement"):
            from .models import SelectedElement
            selected_element = SelectedElement.model_validate(payload["selectedElement"])

        result = run_patch(
            plan=plan,
            design_intent=design_intent,
            manifest=manifest,
            provider_client=provider_client,
            selected_element=selected_element,
        )

        # Persist the record if persistence is available
        if persistence_service is not None:
            try:
                persistence_service.create_patch_record(plan.sessionId, {
                    "id": result.record.id,
                    "patchPlan": plan.model_dump(mode="json"),
                    "status": result.record.status,
                    "filesChanged": result.record.filesChanged,
                    "summary": result.record.summary,
                })
            except Exception:
                pass  # patch record persistence is best-effort

        return {
            "record": result.record.model_dump(mode="json"),
            "validation": {
                "ok": result.validation.ok,
                "errors": result.validation.errors,
                "warnings": result.validation.warnings,
            },
            "filesWritten": result.files_written,
            "rollbackPerformed": result.rollback_performed,
            "error": result.error,
        }

    @app.get("/workspace/files")
    def list_workspace_files() -> dict:
        """List all files in the workspace."""
        from .file_service import list_files
        return {"files": list_files()}

    @app.get("/workspace/file")
    def read_workspace_file(path: str) -> dict:
        """Read a workspace file content."""
        from .file_service import read_file as read_ws_file, file_exists
        if not file_exists(path):
            raise HTTPException(status_code=404, detail=f"File not found: {path}")
        return {"path": path, "content": read_ws_file(path)}

    def require_persistence_service() -> PersistenceService:
        if persistence_service is None:
            raise HTTPException(status_code=503, detail="DATABASE_URL is not configured")
        return persistence_service

    def handle_persistence_error(exc: PersistenceError) -> None:
        if isinstance(exc, NotFoundError):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if isinstance(exc, BadRequestError):
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/sessions", status_code=201)
    def create_session(payload: dict) -> dict:
        service = require_persistence_service()
        try:
            return service.create_session(payload)
        except PersistenceError as exc:
            handle_persistence_error(exc)

    @app.get("/sessions/{session_id}")
    def get_session(session_id: str) -> dict:
        service = require_persistence_service()
        try:
            return service.get_session(session_id)
        except PersistenceError as exc:
            handle_persistence_error(exc)

    @app.post("/sessions/{session_id}/messages", status_code=201)
    def create_message(session_id: str, payload: dict) -> dict:
        service = require_persistence_service()
        try:
            return service.create_message(session_id, payload)
        except PersistenceError as exc:
            handle_persistence_error(exc)

    @app.get("/sessions/{session_id}/messages")
    def list_messages(session_id: str) -> list[dict]:
        service = require_persistence_service()
        try:
            return service.list_messages(session_id)
        except PersistenceError as exc:
            handle_persistence_error(exc)

    @app.put("/sessions/{session_id}/memory")
    def upsert_memory(session_id: str, payload: dict) -> dict:
        service = require_persistence_service()
        try:
            return service.upsert_memory(session_id, payload)
        except PersistenceError as exc:
            handle_persistence_error(exc)

    @app.get("/sessions/{session_id}/memory")
    def get_memory(session_id: str) -> dict:
        service = require_persistence_service()
        try:
            return service.get_memory(session_id)
        except PersistenceError as exc:
            handle_persistence_error(exc)

    @app.post("/sessions/{session_id}/selected-elements", status_code=201)
    def create_selected_element(session_id: str, payload: dict) -> dict:
        service = require_persistence_service()
        try:
            return service.create_selected_element(session_id, payload)
        except PersistenceError as exc:
            handle_persistence_error(exc)

    @app.get("/sessions/{session_id}/selected-elements")
    def list_selected_elements(session_id: str) -> list[dict]:
        service = require_persistence_service()
        try:
            return service.list_selected_elements(session_id)
        except PersistenceError as exc:
            handle_persistence_error(exc)

    @app.post("/sessions/{session_id}/patch-records", status_code=201)
    def create_patch_record(session_id: str, payload: dict) -> dict:
        service = require_persistence_service()
        try:
            return service.create_patch_record(session_id, payload)
        except PersistenceError as exc:
            handle_persistence_error(exc)

    @app.get("/sessions/{session_id}/patch-records")
    def list_patch_records(session_id: str) -> list[dict]:
        service = require_persistence_service()
        try:
            return service.list_patch_records(session_id)
        except PersistenceError as exc:
            handle_persistence_error(exc)

    @app.get("/sessions/{session_id}/restore")
    def restore_session(session_id: str) -> dict:
        service = require_persistence_service()
        try:
            return service.restore_session(session_id)
        except PersistenceError as exc:
            handle_persistence_error(exc)

    # ── Snapshot endpoints (LFG-8) ──────────────────────────────────────────

    @app.post("/sessions/{session_id}/snapshots", status_code=201)
    def create_snapshot_endpoint(session_id: str, payload: dict) -> dict:
        service = require_persistence_service()
        from .snapshot_service import create_snapshot as do_create_snapshot
        try:
            return do_create_snapshot(
                repo=service.repository,
                session_id=session_id,
                label=payload.get("label", ""),
                patch_record_id=payload.get("patchRecordId"),
            )
        except PersistenceError as exc:
            handle_persistence_error(exc)

    @app.get("/sessions/{session_id}/snapshots")
    def list_snapshots_endpoint(session_id: str) -> list[dict]:
        service = require_persistence_service()
        from .snapshot_service import list_snapshots
        try:
            return list_snapshots(repo=service.repository, session_id=session_id)
        except PersistenceError as exc:
            handle_persistence_error(exc)

    @app.post("/snapshots/{snapshot_id}/restore")
    def restore_snapshot_endpoint(snapshot_id: str) -> dict:
        service = require_persistence_service()
        from .snapshot_service import restore_snapshot
        try:
            return restore_snapshot(repo=service.repository, snapshot_id=snapshot_id)
        except PersistenceError as exc:
            handle_persistence_error(exc)

    return app


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("AGENT_PORT", "8123"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
