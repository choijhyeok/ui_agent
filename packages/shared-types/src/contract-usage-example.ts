import type {
  LlmProviderConfig,
  ProjectManifest,
  RuntimeHealth,
  Session,
} from "./index.js";

const provider: LlmProviderConfig = {
  provider: "openai",
  model: "gpt-4.1",
  providerReady: false,
};

const manifest: ProjectManifest = {
  projectId: "bootstrap",
  name: "Local Figma Bootstrap",
  framework: "react",
  runtimePackageManager: "pnpm",
  workspaceRoot: "workspace",
  runtimeEntry: "workspace/preview/index.html",
  files: [{ path: "workspace/preview/index.html", kind: "route", entry: true }],
};

const session: Session = {
  id: "session-bootstrap",
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
  provider,
  manifest,
};

const runtime: RuntimeHealth = {
  projectId: session.manifest.projectId,
  status: "ready",
  runtimeUrl: "http://localhost:3001",
  buildId: "bootstrap",
  lastHeartbeatAt: new Date().toISOString(),
};

void runtime;
