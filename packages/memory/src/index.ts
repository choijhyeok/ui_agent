import type { Message, SelectedElement } from "@local-figma/shared-types";

export interface MemorySnapshot {
  summary: string;
  messages: Message[];
  selectedElements: SelectedElement[];
}
