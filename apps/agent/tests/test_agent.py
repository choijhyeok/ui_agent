from __future__ import annotations

from fastapi.testclient import TestClient

from local_figma_agent.api import create_app
from local_figma_agent import providers


def reset_provider_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4.1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)


def test_health_endpoint_reports_langgraph_ready(monkeypatch):
    reset_provider_env(monkeypatch)
    app = create_app()
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["langgraph"] == "ready"
    assert payload["provider"]["provider"] == "openai"


def test_create_intent_flow_returns_structured_design_intent(monkeypatch):
    reset_provider_env(monkeypatch)
    client = TestClient(create_app())

    response = client.post(
        "/orchestrate",
        json={
            "sessionId": "session-create",
            "message": "Create a dashboard with a hero header and chart panels inspired by OpenAI.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intentKind"] == "create"
    assert payload["designIntent"]["screenType"] == "dashboard"
    assert payload["designIntent"]["styleReferences"][0]["label"] == "OpenAI"
    assert payload["patchPlan"]["strategy"] == "create"


def test_modify_branch_uses_selection_context(monkeypatch):
    reset_provider_env(monkeypatch)
    client = TestClient(create_app())

    response = client.post(
        "/orchestrate",
        json={
            "sessionId": "session-modify",
            "message": "Update this card to use Slack-like interaction cues and a denser layout.",
            "selectedElement": {
                "id": "sel-1",
                "sessionId": "session-modify",
                "selector": "[data-node='card-1']",
                "domPath": ["main", "section", "article"],
                "textSnippet": "Quarterly pipeline",
                "bounds": {"x": 12, "y": 24, "width": 300, "height": 140},
                "sourceHint": {"filePath": "preview/index.html", "exportName": "Card", "line": 12},
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intentKind"] == "style-change"
    assert payload["patchPlan"]["strategy"] == "targeted-update"
    assert payload["patchPlan"]["target"]["selectedElementId"] == "sel-1"
    assert payload["patchPlan"]["target"]["files"] == ["preview/index.html"]
    assert payload["memory"]["selectedElements"][0]["selector"] == "[data-node='card-1']"
    assert "Selection context forwarded" in payload["response"]


def test_layout_restructure_branch(monkeypatch):
    reset_provider_env(monkeypatch)
    client = TestClient(create_app())

    response = client.post(
        "/orchestrate",
        json={
            "sessionId": "session-layout",
            "message": "Reorganize the landing page into a two column layout with a sidebar and keep the footer.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intentKind"] == "layout-restructure"
    assert payload["designIntent"]["layout"]["direction"] == "row"
    assert payload["designIntent"]["lockedConstraints"] == ["Preserve explicitly requested existing structure."]


def test_provider_smoke_uses_mock_when_credentials_missing(monkeypatch):
    reset_provider_env(monkeypatch)
    client = TestClient(create_app())

    response = client.post("/provider/smoke")

    assert response.status_code == 200
    payload = response.json()
    assert payload["invoked"] is True
    assert payload["output"] == "pong"


def test_provider_smoke_uses_openai_sdk_path_when_credentials_exist(monkeypatch):
    reset_provider_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class FakeResponses:
        def create(self, *, model, input):
            assert model == "gpt-4.1"
            assert input == "Return the single word pong."
            return type("FakeResponse", (), {"output_text": "pong-from-sdk"})()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            assert kwargs["api_key"] == "test-key"
            self.responses = FakeResponses()

    monkeypatch.setattr(providers, "OpenAI", FakeOpenAI)
    client = TestClient(create_app())

    response = client.post("/provider/smoke")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "openai"
    assert payload["output"] == "pong-from-sdk"
