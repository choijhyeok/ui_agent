from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


ProviderKind = Literal["openai", "azure-openai"]
PatchStrategy = Literal["create", "update", "targeted-update", "rollback"]
RuntimeStatusKind = Literal["starting", "ready", "degraded", "error"]
IntentKind = Literal["create", "modify", "style-change", "layout-restructure"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LlmProviderConfig(BaseModel):
    provider: ProviderKind
    model: str
    providerReady: bool
    baseUrl: Optional[str] = None
    organization: Optional[str] = None
    azureEndpoint: Optional[str] = None
    azureDeployment: Optional[str] = None
    azureApiVersion: Optional[str] = None


class StyleReference(BaseModel):
    label: str
    source: Optional[str] = None
    influence: Literal["visual", "interaction", "density", "tone"]


class LayoutIntent(BaseModel):
    direction: Literal["row", "column", "mixed"]
    density: Literal["compact", "comfortable", "spacious"]
    regions: list[str] = Field(default_factory=list)


class DesignIntent(BaseModel):
    objective: str
    screenType: str
    layout: LayoutIntent
    tone: list[str] = Field(default_factory=list)
    styleReferences: list[StyleReference] = Field(default_factory=list)
    lockedConstraints: list[str] = Field(default_factory=list)


class ProjectFile(BaseModel):
    path: str
    kind: Literal["route", "component", "style", "asset", "config"]
    entry: Optional[bool] = None


class ProjectManifest(BaseModel):
    projectId: str
    name: str
    framework: Literal["react"]
    runtimePackageManager: Literal["pnpm"]
    workspaceRoot: str
    runtimeEntry: str
    files: list[ProjectFile] = Field(default_factory=list)


class ElementBounds(BaseModel):
    x: float
    y: float
    width: float
    height: float


class SourceHint(BaseModel):
    filePath: Optional[str] = None
    exportName: Optional[str] = None
    line: Optional[int] = None


class SelectedElement(BaseModel):
    id: str
    sessionId: str
    selector: str
    domPath: list[str]
    textSnippet: Optional[str] = None
    bounds: ElementBounds
    sourceHint: Optional[SourceHint] = None
    capturedAt: str = Field(default_factory=utc_now)


class PatchTarget(BaseModel):
    selectedElementId: Optional[str] = None
    intentSummary: str
    files: list[str] = Field(default_factory=list)


class PatchPlan(BaseModel):
    id: str
    sessionId: str
    strategy: PatchStrategy
    target: PatchTarget
    steps: list[str] = Field(default_factory=list)
    validation: list[str] = Field(default_factory=list)


class RuntimeHealth(BaseModel):
    projectId: str
    status: RuntimeStatusKind
    runtimeUrl: str
    buildId: str
    lastHeartbeatAt: str = Field(default_factory=utc_now)
    error: Optional[str] = None


class MessagePart(BaseModel):
    type: Literal["text", "json"]
    value: Any


class SessionMessage(BaseModel):
    id: str
    sessionId: str
    role: Literal["system", "user", "assistant", "tool"]
    parts: list[MessagePart]
    selectedElementId: Optional[str] = None
    createdAt: str = Field(default_factory=utc_now)


class MemorySnapshot(BaseModel):
    summary: str
    selectedElements: list[SelectedElement] = Field(default_factory=list)
    messages: list[SessionMessage] = Field(default_factory=list)


class SessionRecord(BaseModel):
    id: str
    provider: LlmProviderConfig
    manifest: ProjectManifest
    summary: str = ""
    latestDesignIntent: Optional[DesignIntent] = None
    createdAt: str = Field(default_factory=utc_now)
    updatedAt: str = Field(default_factory=utc_now)


class OrchestrationRequest(BaseModel):
    sessionId: str
    message: str
    selectedElement: Optional[SelectedElement] = None
    runtimeStatus: Optional[RuntimeHealth] = None


class ProviderSmokeResult(BaseModel):
    provider: str
    model: str
    invoked: bool
    output: str


class OrchestrationResponse(BaseModel):
    sessionId: str
    intentKind: IntentKind
    designIntent: DesignIntent
    manifest: ProjectManifest
    patchPlan: PatchPlan
    memory: MemorySnapshot
    runtimeStatus: RuntimeHealth
    response: str
    provider: LlmProviderConfig
