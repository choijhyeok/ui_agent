# Local Figma

`HOW-40` established the monorepo skeleton, Docker Compose bootstrap, shared contracts, and reference adoption plan for a local AI-native UI workspace. `HOW-41` adds the first real operator-facing web shell in `apps/web`.

## Workspace layout

```text
apps/
  agent/      LangGraph-oriented orchestration service bootstrap
  runtime/    Live preview runtime bootstrap serving files from workspace/
  web/        Next.js operator workspace shell
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

The current bootstrap exposes:

- Web shell: `http://localhost:3000`
- Agent health/config: `http://localhost:8123/health`
- Agent orchestration: `POST http://localhost:8123/orchestrate`
- Agent provider smoke path: `POST http://localhost:8123/provider/smoke`
- Runtime preview stub: `http://localhost:3001`
- Postgres is only exposed on the internal Docker network by default.

The agent service now runs a minimal LangGraph flow with these stages:

- intent classification
- project state load
- patch planning
- response formatting

Provider selection remains environment-driven through `LLM_PROVIDER`, with `openai` and `azure-openai` normalized behind the same HTTP surface.

If the default published ports are already in use on your machine, override the host bindings before startup:

- `POSTGRES_HOST_PORT=55433 AGENT_HOST_PORT=8124 RUNTIME_HOST_PORT=3002 WEB_HOST_PORT=3003 docker compose up --build`

## Validation

- `docker compose config`
- `corepack pnpm install`
- `pnpm typecheck:contracts`
- `corepack pnpm --filter @local-figma/web typecheck`
- `corepack pnpm --filter @local-figma/web build`

## Key decisions

- Monorepo baseline follows the `OpenGenerativeUI` shape: `apps/*` plus shared packages.
- Selection capability is isolated behind `packages/selection-adapter` because `Agentation` is useful as a reference but ships under PolyForm Shield.
- Shared contracts in `packages/shared-types` are the authority for downstream issues.

Reference analysis and build-vs-fork decisions live in [docs/reference-adoption.md](/Users/jaehyeokchoi/code/local-figma-workspaces/HOW-42/docs/reference-adoption.md). Contract details live in [docs/contracts.md](/Users/jaehyeokchoi/code/local-figma-workspaces/HOW-42/docs/contracts.md).
