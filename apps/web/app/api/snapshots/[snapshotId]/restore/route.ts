import { NextRequest, NextResponse } from "next/server";
import { getWorkspaceServiceUrls } from "@/src/lib/workspace-status";

export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{
    snapshotId: string;
  }>;
};

export async function POST(_request: NextRequest, context: RouteContext) {
  try {
    const { snapshotId } = await context.params;
    const { agentUrl } = getWorkspaceServiceUrls();
    const response = await fetch(`${agentUrl}/snapshots/${snapshotId}/restore`, {
      method: "POST",
      cache: "no-store",
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to restore snapshot" },
      { status: 500 },
    );
  }
}
