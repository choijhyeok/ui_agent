import { NextRequest, NextResponse } from "next/server";
import { getWorkspaceServiceUrls } from "@/src/lib/workspace-status";

export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{
    sessionId: string;
  }>;
};

async function agentFetch(path: string, init?: RequestInit) {
  const { agentUrl } = getWorkspaceServiceUrls();
  return fetch(`${agentUrl}${path}`, { ...init, cache: "no-store" });
}

export async function GET(_request: NextRequest, context: RouteContext) {
  try {
    const { sessionId } = await context.params;
    const response = await agentFetch(`/sessions/${sessionId}/snapshots`);
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to list snapshots" },
      { status: 500 },
    );
  }
}

export async function POST(request: NextRequest, context: RouteContext) {
  try {
    const { sessionId } = await context.params;
    const payload = await request.json();
    const response = await agentFetch(`/sessions/${sessionId}/snapshots`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to create snapshot" },
      { status: 500 },
    );
  }
}
