import type {
  PreviewBridgeEnvelope,
  PreviewHostReadyPayload,
  PreviewRuntimePingPayload,
  PreviewRuntimeReadyPayload,
  PreviewRuntimeReloadPayload,
  PreviewRuntimeReloadedPayload,
  RuntimeHealth,
  SelectedElement,
} from "@local-figma/shared-types";

export const PREVIEW_BRIDGE_VERSION = "2026-03-19";

export type PreviewBridgeToRuntimeEvent =
  | PreviewBridgeEnvelope<"host.ready", PreviewHostReadyPayload>
  | PreviewBridgeEnvelope<"runtime.ping", PreviewRuntimePingPayload>
  | PreviewBridgeEnvelope<"runtime.reload", PreviewRuntimeReloadPayload>;

export type PreviewBridgeToHostEvent =
  | PreviewBridgeEnvelope<"runtime.ready", PreviewRuntimeReadyPayload>
  | PreviewBridgeEnvelope<"runtime.health", RuntimeHealth>
  | PreviewBridgeEnvelope<"runtime.reloaded", PreviewRuntimeReloadedPayload>
  | PreviewBridgeEnvelope<"selection.changed", SelectedElement>;

export type PreviewBridgeEvent = PreviewBridgeToRuntimeEvent | PreviewBridgeToHostEvent;

export function isPreviewBridgeEvent(value: unknown): value is PreviewBridgeEvent {
  if (!value || typeof value !== "object") {
    return false;
  }

  const candidate = value as Partial<PreviewBridgeEvent>;
  return (
    candidate.version === PREVIEW_BRIDGE_VERSION &&
    typeof candidate.type === "string" &&
    typeof candidate.source === "string" &&
    typeof candidate.payload === "object" &&
    candidate.payload !== null
  );
}
