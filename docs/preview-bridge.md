# Preview Bridge Protocol

This issue fixes the runtime preview target at `http://runtime:3001/preview` inside Docker Compose and `http://localhost:3001/preview` for direct local access. The operator shell embeds that URL in an iframe and communicates over `window.postMessage`.

## Transport

- Bridge version: `2026-03-19`
- Parent source: `web`
- Iframe source: `runtime`
- Parent origin: `http://localhost:3000` in local direct runs, `http://web:3000` inside Compose network hops are translated through the browser-facing host URL.
- Runtime origin: `http://localhost:3001` in local direct runs.

The runtime prefers `document.referrer` to derive the parent origin and otherwise falls back to `*`. The parent only accepts messages from the runtime origin configured in `RUNTIME_URL`.

## Parent to runtime messages

### `host.ready`

Sent when the iframe loads or when the operator presses reconnect.

```json
{
  "version": "2026-03-19",
  "source": "web",
  "type": "host.ready",
  "payload": {
    "sessionId": "local-workspace",
    "sentAt": "2026-03-19T10:00:00.000Z"
  }
}
```

Effect: runtime records the host connection and responds with `runtime.ready`.

### `runtime.ping`

Sent after `host.ready` and on manual reconnect.

```json
{
  "version": "2026-03-19",
  "source": "web",
  "type": "runtime.ping",
  "payload": {
    "requestedAt": "2026-03-19T10:00:01.000Z"
  }
}
```

Effect: runtime fetches `/health` and replies with `runtime.health`.

### `runtime.reload`

Reserved for parent-triggered preview reloads.

```json
{
  "version": "2026-03-19",
  "source": "web",
  "type": "runtime.reload",
  "payload": {
    "reason": "manual-refresh",
    "requestedAt": "2026-03-19T10:00:02.000Z"
  }
}
```

Effect: runtime emits `runtime.reloaded` and reloads its document.

## Runtime to parent messages

### `runtime.ready`

Sent on initial boot and after `host.ready`.

Payload:

- `health`: current `RuntimeHealth` snapshot
- `previewPath`: fixed preview route, currently `/preview`

### `runtime.health`

Sent on parent ping and periodic runtime heartbeats. Payload matches `RuntimeHealth` from [packages/shared-types/src/index.ts](/Users/jaehyeokchoi/code/local-figma-workspaces/HOW-43/packages/shared-types/src/index.ts).

Fields:

- `projectId`
- `status`
- `runtimeUrl`
- `buildId`
- `lastHeartbeatAt`
- `error` when readiness fails

### `runtime.reloaded`

Acknowledges a `runtime.reload` request before the iframe refreshes itself.

Payload:

- `reason`
- `reloadedAt`

## Operator controls

- `Refresh iframe`: hard-refreshes the iframe source with a cache-busting query string.
- `Reconnect bridge`: resends `host.ready` and `runtime.ping` without reloading the iframe.

## Endpoints

- `GET /preview`: fixed iframe entrypoint backed by `workspace/preview/index.html`
- `GET /health`: runtime health snapshot with readiness information
- `GET /readyz`: alias for readiness checks
