import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


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


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/health":
            self.send_response(404)
            self.end_headers()
            return

        body = json.dumps(
            {
                "status": "ok",
                "provider": build_provider_status(),
                "databaseUrlConfigured": bool(os.getenv("DATABASE_URL")),
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return


if __name__ == "__main__":
    port = int(os.getenv("AGENT_PORT", "8123"))
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"agent listening on {port}")
    server.serve_forever()
