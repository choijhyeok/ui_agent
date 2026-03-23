import type {
  PatchPlan,
  PatchRecord,
  PatchStrategy,
  PatchStatus,
  SelectedElement,
  DesignIntent,
} from "@local-figma/shared-types";

// ── Re-exports for convenience ─────────────────────────────────────────────
export type { PatchPlan, PatchRecord, PatchStrategy, PatchStatus };

// ── Marker constants (must match Python patch_executor.py) ─────────────────
export const REGION_START_PREFIX = "<!-- @lfg-region:";
export const REGION_END_PREFIX = "<!-- @lfg-region-end:";
export const COMPONENT_ATTR_PREFIX = 'data-lfg-component="';

export const REGION_PATTERN =
  /<!-- @lfg-region:(?<name>[A-Za-z0-9_-]+) -->(?<content>[\s\S]*?)<!-- @lfg-region-end:\k<name> -->/g;

// ── Result types ───────────────────────────────────────────────────────────

export interface PatchValidation {
  ok: boolean;
  errors: string[];
  warnings: string[];
}

export interface PatchEngineResult {
  plan: PatchPlan;
  record?: PatchRecord;
  validation?: PatchValidation;
  filesWritten?: string[];
  rollbackPerformed?: boolean;
  error?: string | null;
}

export interface ExecutePatchRequest {
  patchPlan: PatchPlan;
  designIntent: DesignIntent;
  selectedElement?: SelectedElement;
}

// ── Utility functions ──────────────────────────────────────────────────────

/**
 * Extract the content of a named region from file content.
 * Returns `undefined` if the region is not found.
 */
export function extractRegion(fileContent: string, regionName: string): string | undefined {
  const pattern = new RegExp(
    `<!-- @lfg-region:${regionName} -->([\\s\\S]*?)<!-- @lfg-region-end:${regionName} -->`,
  );
  const match = pattern.exec(fileContent);
  return match ? match[1] : undefined;
}

/**
 * List all region names found in a file.
 */
export function listRegions(fileContent: string): string[] {
  const names: string[] = [];
  const pattern = /<!-- @lfg-region:([A-Za-z0-9_-]+) -->/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(fileContent)) !== null) {
    names.push(match[1]);
  }
  return names;
}

/**
 * Check if content has region markers.
 */
export function hasRegionMarkers(fileContent: string): boolean {
  return fileContent.includes(REGION_START_PREFIX);
}
