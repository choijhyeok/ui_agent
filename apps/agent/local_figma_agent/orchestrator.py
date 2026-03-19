from __future__ import annotations

from typing import Any, Optional
from uuid import uuid4

from langgraph.graph import END, StateGraph

from .models import (
    DesignIntent,
    IntentKind,
    LayoutIntent,
    MemorySnapshot,
    MessagePart,
    OrchestrationRequest,
    PatchPlan,
    PatchTarget,
    RuntimeHealth,
    SelectedElement,
    SessionMessage,
    StyleReference,
    utc_now,
)
from .providers import ProviderClient
from .repository import SessionRepository, build_project_manifest, default_runtime_status


AgentState = dict[str, Any]


def format_instruction(fragment: str) -> str:
    return fragment if fragment.endswith((".", "!", "?")) else f"{fragment}."


def classify_intent_kind(message: str, selected_element: Optional[SelectedElement]) -> IntentKind:
    lowered = message.lower()
    if any(token in lowered for token in ["restyle", "style", "theme", "color", "font", "slack-like", "openai-like", "notion-like", "naver-like"]):
        return "style-change"
    if any(token in lowered for token in ["rearrange", "reorganize", "layout", "move section", "two column"]):
        return "layout-restructure"
    if selected_element or any(token in lowered for token in ["edit", "update", "change", "fix", "this", "selected"]):
        return "modify"
    return "create"


def infer_screen_type(message: str) -> str:
    lowered = message.lower()
    if "dashboard" in lowered:
        return "dashboard"
    if "landing" in lowered or "hero" in lowered:
        return "landing-page"
    if "settings" in lowered:
        return "settings"
    return "workspace"


def infer_direction(message: str) -> str:
    lowered = message.lower()
    if "two column" in lowered or "sidebar" in lowered:
        return "row"
    if "grid" in lowered or "mixed" in lowered:
        return "mixed"
    return "column"


def infer_density(message: str) -> str:
    lowered = message.lower()
    if any(token in lowered for token in ["dense", "compact", "naver"]):
        return "compact"
    if any(token in lowered for token in ["airy", "spacious", "open"]):
        return "spacious"
    return "comfortable"


def infer_regions(message: str) -> list[str]:
    region_map = {
        "hero": "hero",
        "sidebar": "sidebar",
        "header": "header",
        "composer": "composer",
        "table": "table",
        "chart": "chart",
        "footer": "footer",
    }
    lowered = message.lower()
    regions = [value for key, value in region_map.items() if key in lowered]
    return regions or ["header", "content"]


def infer_tone(message: str) -> list[str]:
    lowered = message.lower()
    tone_terms = ["professional", "playful", "minimal", "calm", "technical", "editorial"]
    tones = [term for term in tone_terms if term in lowered]
    return tones or ["product-focused"]


def infer_style_references(message: str) -> list[StyleReference]:
    lowered = message.lower()
    references: list[StyleReference] = []
    catalog = {
        "openai": ("OpenAI", "visual"),
        "slack": ("Slack", "interaction"),
        "notion": ("Notion", "tone"),
        "naver": ("Naver", "density"),
    }
    for token, (label, influence) in catalog.items():
        if token in lowered:
            references.append(StyleReference(label=label, influence=influence))
    return references


def infer_locked_constraints(message: str, selected_element: Optional[SelectedElement]) -> list[str]:
    constraints: list[str] = []
    if "keep" in message.lower():
        constraints.append("Preserve explicitly requested existing structure.")
    if selected_element and selected_element.sourceHint and selected_element.sourceHint.filePath:
        constraints.append(f"Prefer patching {selected_element.sourceHint.filePath} instead of broad regeneration.")
    return constraints


def classify_intent_node(state: AgentState) -> AgentState:
    request: OrchestrationRequest = state["request"]
    intent_kind = classify_intent_kind(request.message, request.selectedElement)
    design_intent = DesignIntent(
        objective=request.message.strip(),
        screenType=infer_screen_type(request.message),
        layout=LayoutIntent(
            direction=infer_direction(request.message),
            density=infer_density(request.message),
            regions=infer_regions(request.message),
        ),
        tone=infer_tone(request.message),
        styleReferences=infer_style_references(request.message),
        lockedConstraints=infer_locked_constraints(request.message, request.selectedElement),
    )

    state["intentKind"] = intent_kind
    state["designIntent"] = design_intent
    return state


def project_state_load_node(state: AgentState) -> AgentState:
    repository: SessionRepository = state["repository"]
    provider = state["providerConfig"]
    manifest = build_project_manifest()
    session = repository.ensure_session(state["request"].sessionId, provider, manifest)
    memory = repository.load_memory(state["request"].sessionId)

    state["manifest"] = session.manifest
    state["memory"] = memory
    state["runtimeStatus"] = state["request"].runtimeStatus or default_runtime_status()
    return state


def planner_node(state: AgentState) -> AgentState:
    request: OrchestrationRequest = state["request"]
    manifest = state["manifest"]
    selected_element = request.selectedElement
    intent_kind: IntentKind = state["intentKind"]
    design_intent: DesignIntent = state["designIntent"]
    memory: MemorySnapshot = state["memory"]

    strategy = "create" if intent_kind == "create" else "update"
    if selected_element:
        strategy = "targeted-update"

    target_files = []
    if selected_element and selected_element.sourceHint and selected_element.sourceHint.filePath:
        target_files.append(selected_element.sourceHint.filePath)
    elif manifest.files:
        target_files.append(manifest.runtimeEntry)

    steps = [
        f"Interpret request as {intent_kind}.",
        f"Use regions {', '.join(design_intent.layout.regions)} with {design_intent.layout.density} density.",
    ]
    if selected_element:
        steps.append(f"Scope changes to selector {selected_element.selector}.")
        if selected_element.componentHint:
            steps.append(f"Treat {selected_element.componentHint} as the primary component hint.")
        if selected_element.note:
            steps.append(f"Honor the operator note: {format_instruction(selected_element.note)}")
    if design_intent.styleReferences:
        labels = ", ".join(reference.label for reference in design_intent.styleReferences)
        steps.append(f"Blend style references: {labels}.")

    validation = [
        "Preview runtime remains healthy after planning.",
        "Target files are constrained to the selected scope when possible.",
        "Patch plan preserves stable component boundaries.",
    ]

    patch_plan = PatchPlan(
        id=f"plan-{uuid4().hex[:8]}",
        sessionId=request.sessionId,
        strategy=strategy,
        target=PatchTarget(
            selectedElementId=selected_element.id if selected_element else None,
            intentSummary=request.message.strip(),
            files=target_files,
        ),
        steps=steps,
        validation=validation,
    )

    summary_segments = [memory.summary] if memory.summary else []
    summary_segments.append(f"Latest request classified as {intent_kind} for {design_intent.screenType}.")
    if selected_element and selected_element.textSnippet:
        summary_segments.append(f"Selection focus: {selected_element.textSnippet}.")
    if selected_element and selected_element.note:
        summary_segments.append(f"Selection note: {selected_element.note}.")
    state["memory"] = MemorySnapshot(
        summary=" ".join(segment for segment in summary_segments if segment).strip(),
        selectedElements=memory.selectedElements + ([selected_element] if selected_element else []),
        messages=memory.messages,
    )
    state["patchPlan"] = patch_plan
    return state


def response_formatting_node(state: AgentState) -> AgentState:
    request: OrchestrationRequest = state["request"]
    repository: SessionRepository = state["repository"]
    memory: MemorySnapshot = state["memory"]
    patch_plan: PatchPlan = state["patchPlan"]
    design_intent: DesignIntent = state["designIntent"]
    intent_kind: IntentKind = state["intentKind"]
    runtime_status: RuntimeHealth = state["runtimeStatus"]

    user_message = SessionMessage(
        id=f"msg-{uuid4().hex[:8]}",
        sessionId=request.sessionId,
        role="user",
        parts=[MessagePart(type="text", value=request.message)],
        selectedElementId=request.selectedElement.id if request.selectedElement else None,
        createdAt=utc_now(),
    )
    assistant_message = SessionMessage(
        id=f"msg-{uuid4().hex[:8]}",
        sessionId=request.sessionId,
        role="assistant",
        parts=[
            MessagePart(
                type="json",
                value={
                    "intentKind": intent_kind,
                    "patchPlanId": patch_plan.id,
                    "runtimeStatus": runtime_status.status,
                },
            )
        ],
        createdAt=utc_now(),
    )
    repository.append_message(user_message, request.selectedElement)
    repository.append_message(assistant_message)
    repository.update_summary(request.sessionId, memory.summary, design_intent.model_dump(mode="json"))

    response_lines = [
        f"Intent classified as {intent_kind}.",
        f"Planned strategy: {patch_plan.strategy}.",
        f"Target files: {', '.join(patch_plan.target.files) if patch_plan.target.files else 'none yet'}.",
    ]
    if request.selectedElement:
        response_lines.append(f"Selection context forwarded: {request.selectedElement.selector}.")
        if request.selectedElement.componentHint:
            response_lines.append(f"Component hint: {request.selectedElement.componentHint}.")
    if design_intent.styleReferences:
        response_lines.append(
            "Style references: "
            + ", ".join(reference.label for reference in design_intent.styleReferences)
            + "."
        )
    state["memory"] = MemorySnapshot(
        summary=memory.summary,
        selectedElements=memory.selectedElements,
        messages=memory.messages + [user_message, assistant_message],
    )
    state["response"] = " ".join(response_lines)
    return state


def _route_from_intent(state: AgentState) -> str:
    return state["intentKind"]


class AgentOrchestrator:
    def __init__(self, repository: SessionRepository, provider_client: ProviderClient, provider_config):
        self.repository = repository
        self.provider_client = provider_client
        self.provider_config = provider_config
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(dict)
        graph.add_node("classify_intent", classify_intent_node)
        graph.add_node("project_state_load", project_state_load_node)
        graph.add_node("planner", planner_node)
        graph.add_node("response_formatting", response_formatting_node)
        graph.set_entry_point("classify_intent")
        graph.add_edge("classify_intent", "project_state_load")
        graph.add_conditional_edges(
            "project_state_load",
            _route_from_intent,
            {
                "create": "planner",
                "modify": "planner",
                "style-change": "planner",
                "layout-restructure": "planner",
            },
        )
        graph.add_edge("planner", "response_formatting")
        graph.add_edge("response_formatting", END)
        return graph.compile()

    def run(self, request: OrchestrationRequest) -> AgentState:
        initial_state: AgentState = {
            "request": request,
            "providerConfig": self.provider_config,
            "repository": self.repository,
            "providerClient": self.provider_client,
        }
        return self.graph.invoke(initial_state)
