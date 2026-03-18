import http from "node:http";
import { createReadStream, existsSync } from "node:fs";
import { stat } from "node:fs/promises";
import { extname, join, normalize } from "node:path";

const port = Number(process.env.RUNTIME_PORT ?? 3001);
const workspaceRoot = "/app/workspace";
const entryPath = join(workspaceRoot, "preview", "index.html");

const contentTypes = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
};

const server = http.createServer(async (req, res) => {
  if (req.url === "/health") {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ status: "ready", entryPath: "workspace/preview/index.html" }));
    return;
  }

  const relativePath = (req.url ?? "/").replace(/^\/+/, "");
  const requested = req.url === "/" ? entryPath : join(workspaceRoot, normalize(relativePath));
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

  res.writeHead(200, { "content-type": contentTypes[extname(requested)] ?? "application/octet-stream" });
  createReadStream(requested).pipe(res);
});

server.listen(port, "0.0.0.0", () => {
  console.log(`runtime listening on ${port}`);
});
