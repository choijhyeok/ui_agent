# Reference Adoption Plan

## References reviewed

- `Agentation` (`fb2d5616606481a79ee6d03abcdd2f227bdbeb8d`, PolyForm Shield 1.0.0): primary reference for selection overlay, selector capture, annotation UX, and source-targeting concepts.
- `OpenGenerativeUI` (`1fde890f2b1baa48b8ef79a3204e4075b5ac1299`, MIT): primary reference for monorepo structure, LangGraph-driven agent service, and live iframe rendering flow.

## Build-vs-fork decisions

| Capability | Primary reference | Decision | Reasoning |
| --- | --- | --- | --- |
| Monorepo layout and app split | OpenGenerativeUI | Reuse with minimal modification | Their `apps/app` + `apps/agent` split maps cleanly to `apps/web`, `apps/agent`, and `apps/runtime`. |
| LangGraph orchestration service shape | OpenGenerativeUI | Adapter | Reuse the service boundary and stateful-agent posture, but keep Local Figma contracts in `packages/shared-types` rather than coupling to CopilotKit-specific schemas. |
| Iframe preview rendering pattern | OpenGenerativeUI | Adapter | Keep the parent/iframe bridge concept and health signaling, but adapt it for a real editable runtime rather than one-shot generated widgets. |
| Selection overlay UX | Agentation | Adapter behind local seam | The UX and selector-capture ideas are strong, but the PolyForm Shield license means foundation should not vendor the code directly into this repository. |
| Selector/source mapping heuristics | Agentation | Intentional reimplementation | Needed for downstream patch precision, but should be implemented locally so we control data format and avoid license entanglement. |
| Structured design intent schema | Neither directly | Reimplement | This is product-specific to Local Figma and needs stable cross-service contracts. |
| Patch planning and history | Neither directly | Reimplement | Existing references do not define Local Figma's constrained edit and audit requirements. |
| Provider abstraction for OpenAI/Azure OpenAI | OpenGenerativeUI as partial reference | Reimplement around shared contract | Foundation needs explicit environment-driven rules that downstream modules can consume uniformly. |

## Borrowed concepts

### From `OpenGenerativeUI`

- `apps/*` monorepo split with a dedicated agent service.
- LangGraph-centric orchestration instead of a thin chat API.
- Live iframe runtime pattern with a parent-controlled rendering surface.
- Dockerized app packaging as the default operator path.

### From `Agentation`

- Selection as a first-class editing primitive, not a debug affordance.
- Capturing DOM selectors, bounds, and source-location hints as structured planner inputs.
- Freeze-and-annotate interaction model for stable element targeting.

## Downstream rules

- Any downstream issue consuming selection data must go through `packages/selection-adapter`.
- Any downstream issue consuming agent state must import contracts from `packages/shared-types`; do not redefine these interfaces ad hoc.
- If a future task wants to embed actual `Agentation` code, it must first document the license impact and why an adapter-only approach is insufficient.
- Runtime/preview work should preserve the `OpenGenerativeUI` style split between parent app responsibilities and preview-side responsibilities.
