# Shared Contracts And Service Boundaries

## Service boundaries

- `apps/web`: operator-facing shell with chat, preview iframe, diff/status surfaces, and selection UX controls.
- `apps/agent`: LangGraph orchestration service that owns prompt interpretation, project state, patch planning, provider selection, and persistence coordination.
- `apps/runtime`: live preview server for generated React app assets under `workspace/`.
- `packages/shared-types`: canonical wire contracts used across web, agent, runtime, and infra.
- `packages/design-schema`: structured design intent shapes layered on top of `shared-types`.
- `packages/preview-bridge`: typed iframe messaging protocol between `web` and `runtime`.
- `packages/selection-adapter`: adapter seam for preview selection, element targeting, and source mapping.
- `packages/patch-engine`: patch planning primitives for constrained file edits.
- `packages/memory`: summary and structured memory helper types for multi-turn persistence.

## Required contracts

The canonical TypeScript definitions are implemented in [packages/shared-types/src/index.ts](/Users/jaehyeokchoi/code/local-figma-workspaces/HOW-44/packages/shared-types/src/index.ts).

### `Session`

Tracks the lifecycle of a user workspace session, including the active provider, manifest reference, and summary timestamps.

### `Message`

Stores a chat turn with role, content parts, and optional selection context reference.

### `DesignIntent`

Structured interpretation of natural-language UI intent, including style references, layout goals, density, constraints, and locked decisions.

### `ProjectManifest`

Declares the workspace project topology, runtime entrypoints, framework metadata, and tracked files.

### `SelectedElement`

Represents a user-selected region or element from the runtime preview, including selectors, DOM path, bounds, and source hints.

### `PatchPlan`

Planner output describing scope, files to touch, strategy, and validation gates for an edit request.

### `PatchRecord`

Persistent audit log for a patch attempt, including plan snapshot, applied files, status, and rollback notes.

### `RuntimeHealth`

Readiness and freshness signal from the runtime preview service, including build ID, project ID, and error state.

### `LlmProviderConfig`

Environment-driven provider config supporting `openai` and `azure-openai` without changing downstream call sites.

## Environment and provider selection rules

- `LLM_PROVIDER` is mandatory. Supported values: `openai`, `azure-openai`. The bootstrap also normalizes `azure` to `azure-openai` so local shells with the shorter alias do not fail during startup.
- `LLM_MODEL` is always required and is interpreted differently by provider:
  - `openai`: model ID such as `gpt-4.1`.
  - `azure-openai`: logical model label for internal use; the actual Azure deployment name is `AZURE_OPENAI_DEPLOYMENT`.
- For `openai`, required vars are `OPENAI_API_KEY`. Optional overrides are `OPENAI_BASE_URL` and `OPENAI_ORG_ID`.
- For `azure-openai`, required vars are `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, and `AZURE_OPENAI_API_VERSION`.
- Provider selection is a startup validation concern owned by `apps/agent`; downstream services consume the normalized `LlmProviderConfig`.
- If credentials are absent, the bootstrap remains runnable but the agent health endpoint reports `providerReady: false`.

## Persistence boundaries

Postgres is the authority for:

- sessions
- messages
- rolling summaries
- selected element snapshots
- patch history
- runtime health snapshots

<<<<<<< HEAD
The bootstrap schema is in [infra/migrations/0001_init.sql](/Users/jaehyeokchoi/code/local-figma-workspaces/HOW-44/infra/migrations/0001_init.sql).
The persistence upgrade for session memory, selected elements, and patch-record enrichment is in [infra/migrations/0002_persistence.sql](/Users/jaehyeokchoi/code/local-figma-workspaces/HOW-44/infra/migrations/0002_persistence.sql).
