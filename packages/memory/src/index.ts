import type { Message, SelectedElement, SessionMemory } from "@local-figma/shared-types";

export interface MemorySnapshot {
  summary: string;
  structuredMemory: SessionMemory["structuredMemory"];
  messages: Message[];
  selectedElements: SelectedElement[];
}
