from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException

from .models import OrchestrationRequest, OrchestrationResponse
from .orchestrator import AgentOrchestrator
from .providers import build_provider_client, load_provider_config
from .repository import SessionRepository
from persistence import BadRequestError, NotFoundError, PersistenceError, PostgresRepository
from service import PersistenceService


def create_app() -> FastAPI:
    app = FastAPI(title="Local Figma Agent", version="0.1.0")

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
            memory=state["memory"],
            runtimeStatus=state["runtimeStatus"],
            response=state["response"],
            provider=provider_config,
        )

    @app.post("/provider/smoke")
    def provider_smoke() -> dict:
        result = provider_client.smoke()
        return result.model_dump(mode="json")

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

    return app


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("AGENT_PORT", "8123"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
