import type {
  LlmProviderConfig,
  PatchPlan,
  ProjectManifest,
  RuntimeHealth,
  SelectedElement,
} from "@local-figma/shared-types";
import { getWorkspaceServiceUrls } from "@/src/lib/workspace-status";

type AgentFetchOptions = {
  method?: "GET" | "POST" | "PUT";
  body?: unknown;
};

type SelectionPersistenceResult = {
  persisted: boolean;
  selectedElement: SelectedElement;
};

type AgentMemorySnapshot = {
  summary: string;
  structuredMemory: Record<string, unknown>;
};

export type OrchestrationResponse = {
  response: string;
  patchPlan: PatchPlan;
  runtimeStatus: RuntimeHealth;
};

function buildFallbackProvider(): LlmProviderConfig {
  return {
    provider: "openai",
    model: process.env.LLM_MODEL ?? "gpt-4.1",
    providerReady: false,
  };
}

function buildSessionManifest(): ProjectManifest {
  return {
    projectId: process.env.PROJECT_NAME ?? "local-figma",
    name: process.env.PROJECT_NAME ?? "Local Figma",
    framework: "react",
    runtimePackageManager: "pnpm",
    workspaceRoot: "workspace",
    runtimeEntry: "preview/index.html",
    files: [
      {
        path: "preview/index.html",
        kind: "route",
        entry: true,
      },
    ],
  };
}

async function agentFetch(path: string, options: AgentFetchOptions = {}) {
  const { agentUrl } = getWorkspaceServiceUrls();
  const response = await fetch(`${agentUrl}${path}`, {
    method: options.method ?? "GET",
    headers: options.body === undefined ? undefined : { "content-type": "application/json" },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    cache: "no-store",
  });

  return response;
}

async function loadProviderConfig(): Promise<LlmProviderConfig> {
  const response = await agentFetch("/health");
  if (!response.ok) {
    return buildFallbackProvider();
  }

  const payload = (await response.json()) as { provider?: LlmProviderConfig };
  return payload.provider ?? buildFallbackProvider();
}

async function ensureSession(sessionId: string): Promise<boolean> {
  const existing = await agentFetch(`/sessions/${sessionId}`);
  if (existing.ok) {
    return true;
  }

  if (existing.status === 503) {
    return false;
  }

  if (existing.status !== 404) {
    const detail = await existing.text();
    throw new Error(`Failed to load session ${sessionId}: ${detail}`);
  }

  const provider = await loadProviderConfig();
  const created = await agentFetch("/sessions", {
    method: "POST",
    body: {
      id: sessionId,
      provider,
      manifest: buildSessionManifest(),
      summary: "",
      structuredMemory: {},
    },
  });

  if (created.status === 503) {
    return false;
  }

  if (!created.ok) {
    const detail = await created.text();
    throw new Error(`Failed to create session ${sessionId}: ${detail}`);
  }

  return true;
}

export async function persistSelectedElement(sessionId: string, selectedElement: SelectedElement): Promise<SelectionPersistenceResult> {
  const persistenceReady = await ensureSession(sessionId);
  if (!persistenceReady) {
    return {
      persisted: false,
      selectedElement,
    };
  }

  const response = await agentFetch(`/sessions/${sessionId}/selected-elements`, {
    method: "POST",
    body: selectedElement,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Failed to persist selected element: ${detail}`);
  }

  const persistedSelection = (await response.json()) as SelectedElement;
  const memoryResponse = await agentFetch(`/sessions/${sessionId}/memory`);
  const existingMemory = memoryResponse.ok
    ? ((await memoryResponse.json()) as AgentMemorySnapshot)
    : {
        summary: "",
        structuredMemory: {},
      };

  await agentFetch(`/sessions/${sessionId}/memory`, {
    method: "PUT",
    body: {
      summary: existingMemory.summary,
      structuredMemory: {
        ...existingMemory.structuredMemory,
        selectedElementId: persistedSelection.id,
        selector: persistedSelection.selector,
        componentHint: persistedSelection.componentHint ?? null,
        note: persistedSelection.note ?? null,
      },
    },
  });

  return {
    persisted: true,
    selectedElement: persistedSelection,
  };
}

export async function orchestrateSelectionRequest(payload: {
  sessionId: string;
  message: string;
  selectedElement?: SelectedElement | null;
  runtimeStatus?: RuntimeHealth;
}): Promise<OrchestrationResponse> {
  await ensureSession(payload.sessionId);

  const response = await agentFetch("/orchestrate", {
    method: "POST",
    body: payload,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Failed to orchestrate request: ${detail}`);
  }

  return (await response.json()) as OrchestrationResponse;
}
