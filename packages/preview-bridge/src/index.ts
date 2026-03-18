import type { RuntimeHealth, SelectedElement } from "@local-figma/shared-types";

export type PreviewBridgeEvent =
  | { type: "runtime.health"; payload: RuntimeHealth }
  | { type: "selection.changed"; payload: SelectedElement }
  | { type: "runtime.reload"; payload: { reason: string } };
