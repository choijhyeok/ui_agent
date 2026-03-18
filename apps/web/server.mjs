import http from "node:http";

const port = Number(process.env.WEB_PORT ?? 3000);
const agentUrl = process.env.AGENT_URL ?? "http://localhost:8123";
const runtimeUrl = process.env.RUNTIME_URL ?? "http://localhost:3001";
const runtimePreviewUrl = `${runtimeUrl.replace(/\/$/, "")}/preview`;

const html = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Local Figma Workspace</title>
    <style>
      :root {
        color: #102a43;
        background:
          radial-gradient(circle at top, rgba(14, 165, 233, 0.18), transparent 20rem),
          linear-gradient(160deg, #fff8e7, #d9f0ff 60%, #eff6ff);
        font-family: "Space Grotesk", sans-serif;
      }
      * {
        box-sizing: border-box;
      }
      body {
        margin: 0;
      }
      .shell {
        display: grid;
        grid-template-columns: minmax(20rem, 26rem) 1fr;
        min-height: 100vh;
      }
      aside, main {
        padding: 2rem;
      }
      aside {
        background: rgba(16, 42, 67, 0.92);
        color: #f0f4f8;
      }
      .controls {
        display: flex;
        flex-wrap: wrap;
        gap: 0.75rem;
        margin: 1.25rem 0;
      }
      .status-list {
        display: grid;
        gap: 0.75rem;
        margin-top: 1.25rem;
      }
      .status-item,
      .card {
        background: rgba(255, 255, 255, 0.78);
        border-radius: 1.25rem;
        box-shadow: 0 20px 40px rgba(16, 42, 67, 0.12);
        padding: 1rem 1.25rem;
      }
      .status-item strong {
        display: block;
        margin-bottom: 0.35rem;
      }
      button {
        border: 0;
        border-radius: 999px;
        background: #0f766e;
        color: white;
        cursor: pointer;
        font: inherit;
        padding: 0.7rem 1rem;
      }
      button.secondary {
        background: #1d4ed8;
      }
      iframe {
        width: 100%;
        min-height: 72vh;
        border: 0;
        border-radius: 1rem;
        background: white;
      }
      code {
        padding: 0.1rem 0.35rem;
        border-radius: 0.3rem;
        background: rgba(16, 42, 67, 0.1);
      }
      .hint {
        color: #486581;
        font-size: 0.95rem;
      }
      @media (max-width: 960px) {
        .shell {
          grid-template-columns: 1fr;
        }
      }
    </style>
  </head>
  <body>
    <div class="shell">
      <aside>
        <h1>Local Figma</h1>
        <p>Runtime bridge integration shell for the generated preview iframe.</p>
        <p>Agent: <code>${agentUrl}</code></p>
        <p>Runtime base: <code>${runtimeUrl}</code></p>
        <p>Preview URL: <code>${runtimePreviewUrl}</code></p>
        <div class="controls">
          <button id="refresh-preview" type="button">Refresh iframe</button>
          <button id="reconnect-preview" class="secondary" type="button">Reconnect bridge</button>
        </div>
        <div class="status-list">
          <div class="status-item">
            <strong>Bridge</strong>
            <span id="bridge-status">Connecting</span>
          </div>
          <div class="status-item">
            <strong>Runtime</strong>
            <span id="runtime-status">Unknown</span>
          </div>
          <div class="status-item">
            <strong>Build</strong>
            <span id="build-id">Unknown</span>
          </div>
          <div class="status-item">
            <strong>Last event</strong>
            <span id="last-event">Waiting for runtime</span>
          </div>
        </div>
      </aside>
      <main>
        <div class="card">
          <h2>Preview iframe</h2>
          <p class="hint">The parent shell keeps a fixed preview target and can either send a bridge reconnect ping or hard-refresh the iframe source.</p>
          <iframe id="preview-frame" src="${runtimePreviewUrl}" title="Local Figma runtime preview"></iframe>
        </div>
      </main>
    </div>
    <script>
      const bridgeVersion = "2026-03-19";
      const runtimeUrl = ${JSON.stringify(runtimeUrl)};
      const runtimePreviewUrl = ${JSON.stringify(runtimePreviewUrl)};
      const runtimeOrigin = new URL(runtimeUrl).origin;
      const frame = document.getElementById("preview-frame");
      const bridgeStatus = document.getElementById("bridge-status");
      const runtimeStatus = document.getElementById("runtime-status");
      const buildId = document.getElementById("build-id");
      const lastEvent = document.getElementById("last-event");

      function sendBridgeMessage(type, payload) {
        if (!frame.contentWindow) {
          return;
        }

        frame.contentWindow.postMessage({
          version: bridgeVersion,
          source: "web",
          type,
          payload,
        }, runtimeOrigin);
      }

      function updateHealth(payload) {
        bridgeStatus.textContent = "Connected";
        runtimeStatus.textContent = payload.status;
        buildId.textContent = payload.buildId;
        lastEvent.textContent = "runtime.health @ " + new Date(payload.lastHeartbeatAt).toLocaleTimeString();
      }

      function handshake() {
        bridgeStatus.textContent = "Connecting";
        sendBridgeMessage("host.ready", {
          sentAt: new Date().toISOString(),
          sessionId: "local-workspace",
        });
        sendBridgeMessage("runtime.ping", {
          requestedAt: new Date().toISOString(),
        });
      }

      frame.addEventListener("load", () => {
        lastEvent.textContent = "iframe load @ " + new Date().toLocaleTimeString();
        handshake();
      });

      window.addEventListener("message", (event) => {
        if (event.origin !== runtimeOrigin) {
          return;
        }

        const data = event.data;
        if (!data || data.version !== bridgeVersion || data.source !== "runtime") {
          return;
        }

        if (data.type === "runtime.ready") {
          updateHealth(data.payload.health);
          lastEvent.textContent = "runtime.ready @ " + new Date().toLocaleTimeString();
          return;
        }

        if (data.type === "runtime.health") {
          updateHealth(data.payload);
          return;
        }

        if (data.type === "runtime.reloaded") {
          bridgeStatus.textContent = "Reload requested";
          lastEvent.textContent = "runtime.reloaded (" + data.payload.reason + ")";
        }
      });

      document.getElementById("refresh-preview").addEventListener("click", () => {
        bridgeStatus.textContent = "Refreshing iframe";
        frame.src = runtimePreviewUrl + "?refresh=" + Date.now();
      });

      document.getElementById("reconnect-preview").addEventListener("click", () => {
        bridgeStatus.textContent = "Reconnecting";
        handshake();
      });
    </script>
  </body>
</html>`;

const server = http.createServer((req, res) => {
  if (req.url === "/health") {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ status: "ok", agentUrl, runtimeUrl, runtimePreviewUrl }));
    return;
  }

  res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
  res.end(html);
});

server.listen(port, "0.0.0.0", () => {
  console.log(`web listening on ${port}`);
});
