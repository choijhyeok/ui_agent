import type { PatchPlan, PatchRecord } from "@local-figma/shared-types";

export interface PatchEngineResult {
  plan: PatchPlan;
  record?: PatchRecord;
}
