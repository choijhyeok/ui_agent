type ServiceState = "ready" | "degraded" | "error";

export interface ServiceHealthSnapshot {
  label: string;
  url: string;
  state: ServiceState;
  summary: string;
  detail: string;
  raw?: unknown;
}

export interface WorkspaceStatusSnapshot {
  checkedAt: string;
  agent: ServiceHealthSnapshot;
  runtime: ServiceHealthSnapshot;
}

export function getWorkspaceUrls() {
  return {
    agentUrl: process.env.AGENT_URL ?? process.env.AGENT_SERVER_URL ?? "http://localhost:8123",
    runtimeUrl: process.env.RUNTIME_URL ?? "http://localhost:3001",
  };
}

function getWorkspaceServiceUrls() {
  return {
    agentUrl: process.env.AGENT_SERVER_URL ?? process.env.AGENT_URL ?? "http://localhost:8123",
    runtimeUrl: process.env.RUNTIME_SERVER_URL ?? process.env.RUNTIME_URL ?? "http://localhost:3001",
  };
}

async function fetchJson(url: string) {
  try {
    const response = await fetch(url, {
      cache: "no-store",
      signal: AbortSignal.timeout(2_500),
    });

    if (!response.ok) {
      return {
        ok: false as const,
        status: response.status,
        body: await response.text(),
      };
    }

    return {
      ok: true as const,
      status: response.status,
      body: (await response.json()) as Record<string, unknown>,
    };
  } catch (error) {
    return {
      ok: false as const,
      status: 0,
      body: error instanceof Error ? error.message : "Unknown fetch error",
    };
  }
}

function normalizeAgentHealth(url: string, payload: Awaited<ReturnType<typeof fetchJson>>): ServiceHealthSnapshot {
  if (!payload.ok) {
    return {
      label: "Agent",
      url,
      state: "error",
      summary: "offline",
      detail: typeof payload.body === "string" ? payload.body : `HTTP ${payload.status}`,
    };
  }

  const provider = payload.body.provider as Record<string, unknown> | undefined;
  const providerReady = Boolean(provider?.providerReady);
  const providerLabel = `${String(provider?.provider ?? "unknown")} / ${String(provider?.model ?? "unknown")}`;

  return {
    label: "Agent",
    url,
    state: providerReady ? "ready" : "degraded",
    summary: providerReady ? "connected" : "credentials missing",
    detail: providerReady ? providerLabel : `${providerLabel}, provider not fully configured`,
    raw: payload.body,
  };
}

function normalizeRuntimeHealth(url: string, payload: Awaited<ReturnType<typeof fetchJson>>): ServiceHealthSnapshot {
  if (!payload.ok) {
    return {
      label: "Runtime",
      url,
      state: "error",
      summary: "offline",
      detail: typeof payload.body === "string" ? payload.body : `HTTP ${payload.status}`,
    };
  }

  const status = String(payload.body.status ?? "unknown");
  return {
    label: "Runtime",
    url,
    state: status === "ready" ? "ready" : "degraded",
    summary: status,
    detail: String(payload.body.entryPath ?? "health endpoint reachable"),
    raw: payload.body,
  };
}

export async function getWorkspaceStatus(): Promise<WorkspaceStatusSnapshot> {
  const urls = getWorkspaceUrls();
  const serviceUrls = getWorkspaceServiceUrls();
  const [agentHealth, runtimeHealth] = await Promise.all([
    fetchJson(`${serviceUrls.agentUrl}/health`),
    fetchJson(`${serviceUrls.runtimeUrl}/health`),
  ]);

  return {
    checkedAt: new Date().toISOString(),
    agent: normalizeAgentHealth(urls.agentUrl, agentHealth),
    runtime: normalizeRuntimeHealth(urls.runtimeUrl, runtimeHealth),
  };
}
