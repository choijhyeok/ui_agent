import type { SelectedElement } from "@local-figma/shared-types";

export interface SelectionAdapter {
  mode: "agentation-compatible" | "internal";
  captureSelection(): Promise<SelectedElement | null>;
}
