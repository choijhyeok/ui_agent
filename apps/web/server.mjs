import http from "node:http";

const port = Number(process.env.WEB_PORT ?? 3000);
const agentUrl = process.env.AGENT_URL ?? "http://localhost:8123";
const runtimeUrl = process.env.RUNTIME_URL ?? "http://localhost:3001";

const html = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Local Figma Workspace</title>
    <style>
      :root {
        font-family: "Space Grotesk", sans-serif;
        color: #102a43;
        background:
          radial-gradient(circle at top, rgba(14, 165, 233, 0.18), transparent 20rem),
          linear-gradient(160deg, #fff8e7, #d9f0ff 60%, #eff6ff);
      }
      body { margin: 0; }
      .shell {
        min-height: 100vh;
        display: grid;
        grid-template-columns: minmax(20rem, 26rem) 1fr;
      }
      aside, main { padding: 2rem; }
      aside {
        background: rgba(16, 42, 67, 0.92);
        color: #f0f4f8;
      }
      .card {
        border-radius: 1.25rem;
        background: rgba(255, 255, 255, 0.75);
        box-shadow: 0 20px 40px rgba(16, 42, 67, 0.12);
        padding: 1.5rem;
      }
      iframe {
        width: 100%;
        min-height: 70vh;
        border: 0;
        border-radius: 1rem;
        background: white;
      }
      code {
        padding: 0.1rem 0.35rem;
        border-radius: 0.3rem;
        background: rgba(16, 42, 67, 0.1);
      }
    </style>
  </head>
  <body>
    <div class="shell">
      <aside>
        <h1>Local Figma</h1>
        <p>Foundation workspace shell. Downstream issues will replace this bootstrap with the real Next.js operator app.</p>
        <p>Agent: <code>${agentUrl}</code></p>
        <p>Runtime: <code>${runtimeUrl}</code></p>
      </aside>
      <main>
        <div class="card">
          <h2>Preview iframe</h2>
          <iframe src="${runtimeUrl}" title="Local Figma runtime preview"></iframe>
        </div>
      </main>
    </div>
  </body>
</html>`;

const server = http.createServer((req, res) => {
  if (req.url === "/health") {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ status: "ok", agentUrl, runtimeUrl }));
    return;
  }

  res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
  res.end(html);
});

server.listen(port, "0.0.0.0", () => {
  console.log(`web listening on ${port}`);
});
