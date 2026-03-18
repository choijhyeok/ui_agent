# Local Figma Foundation

`HOW-40` establishes the monorepo skeleton, Docker Compose bootstrap, shared contracts, and reference adoption plan for a local AI-native UI workspace.

## Workspace layout

```text
apps/
  agent/      LangGraph-oriented orchestration service bootstrap
  runtime/    Live preview runtime bootstrap serving files from workspace/
  web/        Operator workspace shell bootstrap
packages/
  shared-types/       Cross-service contracts
  design-schema/      Structured design intent helpers
  memory/             Session and summary helpers
  patch-engine/       Patch planning contract seam
  preview-bridge/     Parent/iframe event protocol
  selection-adapter/  Selection overlay adapter seam
infra/
  migrations/         Postgres schema bootstrap
workspace/
  preview/            Generated runtime files placeholder
docs/
  contracts.md
  reference-adoption.md
```

## Quick start

1. Copy `.env.example` to `.env`.
2. Fill the provider credentials for either OpenAI or Azure OpenAI.
3. Run `docker compose up --build`.

The foundation bootstrap exposes:

- Web shell: `http://localhost:3000`
- Agent health/config: `http://localhost:8123/health`
- Agent orchestration: `POST http://localhost:8123/orchestrate`
- Agent provider smoke path: `POST http://localhost:8123/provider/smoke`
- Runtime preview stub: `http://localhost:3001`
- Postgres: `localhost:55432`

The agent service now runs a minimal LangGraph flow with these stages:

- intent classification
- project state load
- patch planning
- response formatting

Provider selection remains environment-driven through `LLM_PROVIDER`, with `openai` and `azure-openai` normalized behind the same HTTP surface.

## Validation

- `docker compose config`
- `pnpm install`
- `pnpm typecheck:contracts`

## Key decisions

- Monorepo baseline follows the `OpenGenerativeUI` shape: `apps/*` plus shared packages.
- Selection capability is isolated behind `packages/selection-adapter` because `Agentation` is useful as a reference but ships under PolyForm Shield.
- Shared contracts in `packages/shared-types` are the authority for downstream issues.

Reference analysis and build-vs-fork decisions live in [docs/reference-adoption.md](/Users/jaehyeokchoi/code/local-figma-workspaces/HOW-40/docs/reference-adoption.md). Contract details live in [docs/contracts.md](/Users/jaehyeokchoi/code/local-figma-workspaces/HOW-40/docs/contracts.md).
