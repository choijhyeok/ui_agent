export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };
export type BridgeMessageSource = "web" | "runtime";

export type MessageRole = "system" | "user" | "assistant" | "tool";
export type ProviderKind = "openai" | "azure-openai";
export type PatchStrategy = "create" | "update" | "targeted-update" | "rollback";
export type PatchStatus = "planned" | "applied" | "failed" | "rolled-back";
export type RuntimeStatus = "starting" | "ready" | "degraded" | "error";

export interface LlmProviderConfig {
  provider: ProviderKind;
  model: string;
  baseUrl?: string;
  organization?: string;
  azureEndpoint?: string;
  azureDeployment?: string;
  azureApiVersion?: string;
  providerReady: boolean;
}

export interface MessagePart {
  type: "text" | "json";
  value: string | JsonValue;
}

export interface Message {
  id: string;
  sessionId: string;
  role: MessageRole;
  parts: MessagePart[];
  selectedElementId?: string;
  createdAt: string;
}

export interface StyleReference {
  label: string;
  source?: string;
  influence: "visual" | "interaction" | "density" | "tone";
}

export interface DesignIntent {
  objective: string;
  screenType: string;
  layout: {
    direction: "row" | "column" | "mixed";
    density: "compact" | "comfortable" | "spacious";
    regions: string[];
  };
  tone: string[];
  styleReferences: StyleReference[];
  lockedConstraints: string[];
}

export interface ProjectFile {
  path: string;
  kind: "route" | "component" | "style" | "asset" | "config";
  entry?: boolean;
}

export interface ProjectManifest {
  projectId: string;
  name: string;
  framework: "react";
  runtimePackageManager: "pnpm";
  workspaceRoot: string;
  runtimeEntry: string;
  files: ProjectFile[];
}

export interface ElementBounds {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface SelectedElement {
  id: string;
  sessionId: string;
  kind: "element" | "area";
  selector: string;
  domPath: string[];
  textSnippet?: string;
  bounds: ElementBounds;
  note?: string;
  componentHint?: string;
  sourceHint?: {
    filePath?: string;
    exportName?: string;
    line?: number;
  };
  capturedAt: string;
}

export interface PatchPlan {
  id: string;
  sessionId: string;
  strategy: PatchStrategy;
  target: {
    selectedElementId?: string;
    intentSummary: string;
    files: string[];
  };
  steps: string[];
  validation: string[];
}

export interface PatchRecord {
  id: string;
  sessionId: string;
  planId: string;
  status: PatchStatus;
  filesChanged: string[];
  summary: string;
  createdAt: string;
}

export interface RuntimeHealth {
  projectId: string;
  status: RuntimeStatus;
  runtimeUrl: string;
  buildId: string;
  lastHeartbeatAt: string;
  error?: string;
}

export interface SessionMemory {
  sessionId: string;
  summary: string;
  structuredMemory: Record<string, JsonValue>;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface PreviewBridgeEnvelope<TType extends string, TPayload extends JsonValue | object> {
  version: "2026-03-19";
  source: BridgeMessageSource;
  type: TType;
  payload: TPayload;
}

export interface PreviewHostReadyPayload {
  sessionId?: string;
  sentAt: string;
}

export interface PreviewRuntimePingPayload {
  requestedAt: string;
}

export interface PreviewRuntimeReloadPayload {
  reason: string;
  requestedAt: string;
}

export interface PreviewRuntimeReadyPayload {
  health: RuntimeHealth;
  previewPath: string;
}

export interface PreviewRuntimeReloadedPayload {
  reason: string;
  reloadedAt: string;
}

export interface Session {
  id: string;
  createdAt: string;
  updatedAt: string;
  provider: LlmProviderConfig;
  manifest: ProjectManifest;
  summary?: string;
  latestDesignIntent?: DesignIntent;
}

export interface SessionRestoreSnapshot {
  session: Session;
  memory: SessionMemory;
  messages: Message[];
  selectedElements: SelectedElement[];
  patchRecords: PatchRecord[];
}
