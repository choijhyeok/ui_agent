import json
import os
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

from persistence import BadRequestError, NotFoundError, PersistenceError, PostgresRepository
from service import PersistenceService


def build_provider_status() -> dict:
    raw_provider = os.getenv("LLM_PROVIDER", "openai")
    provider = "azure-openai" if raw_provider == "azure" else raw_provider
    model = os.getenv("LLM_MODEL", "gpt-4.1")

    if provider == "azure-openai":
        ready = all(
            [
                os.getenv("AZURE_OPENAI_API_KEY"),
                os.getenv("AZURE_OPENAI_ENDPOINT"),
                os.getenv("AZURE_OPENAI_DEPLOYMENT"),
                os.getenv("AZURE_OPENAI_API_VERSION"),
            ]
        )
        return {
            "provider": provider,
            "model": model,
            "providerReady": ready,
            "azureEndpoint": os.getenv("AZURE_OPENAI_ENDPOINT"),
            "azureDeployment": os.getenv("AZURE_OPENAI_DEPLOYMENT"),
            "azureApiVersion": os.getenv("AZURE_OPENAI_API_VERSION"),
        }

    ready = bool(os.getenv("OPENAI_API_KEY"))
    return {
        "provider": "openai",
        "model": model,
        "providerReady": ready,
        "baseUrl": os.getenv("OPENAI_BASE_URL"),
        "organization": os.getenv("OPENAI_ORG_ID"),
    }


SESSION_ROUTE = re.compile(r"^/sessions/([^/]+)$")
SESSION_COLLECTION_CHILD_ROUTE = re.compile(r"^/sessions/([^/]+)/(messages|memory|selected-elements|patch-records|restore)$")


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict | list) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    content_length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(content_length) if content_length else b"{}"
    try:
        return json.loads(raw or b"{}")
    except json.JSONDecodeError as exc:
        raise BadRequestError(f"invalid JSON body: {exc.msg}") from exc


def build_handler(service: PersistenceService):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            try:
                self._handle_get()
            except NotFoundError as exc:
                _json_response(self, HTTPStatus.NOT_FOUND, {"error": str(exc)})
            except PersistenceError as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except Exception as exc:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

        def do_POST(self) -> None:
            try:
                self._handle_post()
            except NotFoundError as exc:
                _json_response(self, HTTPStatus.NOT_FOUND, {"error": str(exc)})
            except PersistenceError as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except Exception as exc:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

        def do_PUT(self) -> None:
            try:
                self._handle_put()
            except NotFoundError as exc:
                _json_response(self, HTTPStatus.NOT_FOUND, {"error": str(exc)})
            except PersistenceError as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except Exception as exc:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

        def _handle_get(self) -> None:
            path = urlparse(self.path).path
            if path == "/health":
                persistence_health = service.health()
                status = HTTPStatus.OK if persistence_health["databaseReady"] else HTTPStatus.SERVICE_UNAVAILABLE
                _json_response(
                    self,
                    status,
                    {
                        "status": "ok" if persistence_health["databaseReady"] else "degraded",
                        "provider": build_provider_status(),
                        "databaseUrlConfigured": bool(os.getenv("DATABASE_URL")),
                        **persistence_health,
                    },
                )
                return

            route_match = SESSION_ROUTE.match(path)
            if route_match:
                _json_response(self, HTTPStatus.OK, service.get_session(route_match.group(1)))
                return

            child_match = SESSION_COLLECTION_CHILD_ROUTE.match(path)
            if not child_match:
                _json_response(self, HTTPStatus.NOT_FOUND, {"error": f"route {path} not found"})
                return

            session_id, resource = child_match.groups()
            if resource == "messages":
                _json_response(self, HTTPStatus.OK, service.list_messages(session_id))
                return
            if resource == "memory":
                _json_response(self, HTTPStatus.OK, service.get_memory(session_id))
                return
            if resource == "selected-elements":
                _json_response(self, HTTPStatus.OK, service.list_selected_elements(session_id))
                return
            if resource == "patch-records":
                _json_response(self, HTTPStatus.OK, service.list_patch_records(session_id))
                return
            if resource == "restore":
                _json_response(self, HTTPStatus.OK, service.restore_session(session_id))
                return

            _json_response(self, HTTPStatus.NOT_FOUND, {"error": f"route {path} not found"})

        def _handle_post(self) -> None:
            path = urlparse(self.path).path
            if path == "/sessions":
                _json_response(self, HTTPStatus.CREATED, service.create_session(_read_json(self)))
                return

            child_match = SESSION_COLLECTION_CHILD_ROUTE.match(path)
            if not child_match:
                _json_response(self, HTTPStatus.NOT_FOUND, {"error": f"route {path} not found"})
                return

            session_id, resource = child_match.groups()
            payload = _read_json(self)
            if resource == "messages":
                _json_response(self, HTTPStatus.CREATED, service.create_message(session_id, payload))
                return
            if resource == "selected-elements":
                _json_response(self, HTTPStatus.CREATED, service.create_selected_element(session_id, payload))
                return
            if resource == "patch-records":
                _json_response(self, HTTPStatus.CREATED, service.create_patch_record(session_id, payload))
                return

            _json_response(self, HTTPStatus.METHOD_NOT_ALLOWED, {"error": f"POST not supported for {path}"})

        def _handle_put(self) -> None:
            path = urlparse(self.path).path
            child_match = SESSION_COLLECTION_CHILD_ROUTE.match(path)
            if not child_match:
                _json_response(self, HTTPStatus.NOT_FOUND, {"error": f"route {path} not found"})
                return

            session_id, resource = child_match.groups()
            if resource != "memory":
                _json_response(self, HTTPStatus.METHOD_NOT_ALLOWED, {"error": f"PUT not supported for {path}"})
                return

            _json_response(self, HTTPStatus.OK, service.upsert_memory(session_id, _read_json(self)))

        def log_message(self, format: str, *args) -> None:
            return

    return Handler


def create_server() -> HTTPServer:
    port = int(os.getenv("AGENT_PORT", "8123"))
    repository = PostgresRepository()
    service = PersistenceService(repository)
    return HTTPServer(("0.0.0.0", port), build_handler(service))


if __name__ == "__main__":
    server = create_server()
    port = int(os.getenv("AGENT_PORT", "8123"))
    print(f"agent listening on {port}")
    server.serve_forever()
