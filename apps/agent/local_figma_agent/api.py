from __future__ import annotations

import os

from fastapi import FastAPI

from .models import OrchestrationRequest, OrchestrationResponse
from .orchestrator import AgentOrchestrator
from .providers import build_provider_client, load_provider_config
from .repository import SessionRepository


def create_app() -> FastAPI:
    app = FastAPI(title="Local Figma Agent", version="0.1.0")

    provider_config = load_provider_config()
    repository = SessionRepository()
    provider_client = build_provider_client(provider_config)
    orchestrator = AgentOrchestrator(repository, provider_client, provider_config)

    @app.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "provider": provider_config.model_dump(mode="json"),
            "databaseUrlConfigured": repository.is_configured(),
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

    return app


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("AGENT_PORT", "8123"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
