import http from "node:http";
import { createReadStream, existsSync } from "node:fs";
import { stat } from "node:fs/promises";
import { extname, join, normalize, resolve } from "node:path";

const port = Number(process.env.RUNTIME_PORT ?? 3001);
const projectId = process.env.RUNTIME_PROJECT_ID ?? "local-figma-preview";
const runtimePublicUrl = process.env.RUNTIME_PUBLIC_URL ?? `http://localhost:${port}`;
const workspaceRoot = process.env.WORKSPACE_ROOT ?? resolve(process.cwd(), "workspace");
const previewPath = "/preview";
const entryPath = join(workspaceRoot, "preview", "index.html");

const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
};

async function buildRuntimeHealth() {
  try {
    const info = await stat(entryPath);
    return {
      buildId: `${info.mtimeMs}`,
      lastHeartbeatAt: new Date().toISOString(),
      projectId,
      runtimeUrl: runtimePublicUrl,
      status: "ready",
    };
  } catch (error) {
    return {
      buildId: "missing-entry",
      error: error instanceof Error ? error.message : "Preview entry missing",
      lastHeartbeatAt: new Date().toISOString(),
      projectId,
      runtimeUrl: runtimePublicUrl,
      status: "error",
    };
  }
}

function sendJson(res, statusCode, payload) {
  res.writeHead(statusCode, {
    "cache-control": "no-store",
    "content-type": "application/json; charset=utf-8",
  });
  res.end(JSON.stringify(payload));
}

function resolveWorkspacePath(urlPath) {
  const relativePath = urlPath.replace(/^\/+/, "");
  const normalizedPath = normalize(relativePath);
  return join(workspaceRoot, normalizedPath);
}

const server = http.createServer(async (req, res) => {
  const requestUrl = new URL(req.url ?? "/", `http://${req.headers.host ?? "127.0.0.1"}`);
  const pathname = requestUrl.pathname;

  if (pathname === "/health" || pathname === "/readyz") {
    const health = await buildRuntimeHealth();
    sendJson(res, health.status === "ready" ? 200 : 503, health);
    return;
  }

  if (pathname === "/" || pathname === previewPath) {
    if (!existsSync(entryPath)) {
      res.writeHead(503, { "content-type": "text/plain; charset=utf-8" });
      res.end("Preview entry not found");
      return;
    }

    res.writeHead(200, {
      "cache-control": "no-store",
      "content-type": "text/html; charset=utf-8",
    });
    createReadStream(entryPath).pipe(res);
    return;
  }

  const requested = resolveWorkspacePath(pathname);
  if (!requested.startsWith(workspaceRoot) || !existsSync(requested)) {
    res.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
    res.end("Not found");
    return;
  }

  const info = await stat(requested);
  if (info.isDirectory()) {
    res.writeHead(403, { "content-type": "text/plain; charset=utf-8" });
    res.end("Directory listing disabled");
    return;
  }

  res.writeHead(200, {
    "cache-control": extname(requested) === ".html" ? "no-store" : "public, max-age=60",
    "content-type": contentTypes[extname(requested)] ?? "application/octet-stream",
  });
  createReadStream(requested).pipe(res);
});

server.listen(port, "0.0.0.0", () => {
  console.log(`runtime listening on ${port}`);
});
