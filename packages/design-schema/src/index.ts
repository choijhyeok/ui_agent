import type { DesignIntent } from "@local-figma/shared-types";

export interface DesignAxis {
  name: "layout" | "density" | "tone" | "brand-reference";
  value: string;
}

export interface StructuredDesignIntent {
  intent: DesignIntent;
  axes: DesignAxis[];
}
