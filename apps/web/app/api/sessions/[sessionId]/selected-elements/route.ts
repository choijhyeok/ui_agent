import { NextRequest, NextResponse } from "next/server";
import type { SelectedElement } from "@local-figma/shared-types";
import { persistSelectedElement } from "@/src/lib/agent-api";

export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{
    sessionId: string;
  }>;
};

export async function POST(request: NextRequest, context: RouteContext) {
  try {
    const { sessionId } = await context.params;
    const payload = (await request.json()) as SelectedElement;
    const response = await persistSelectedElement(sessionId, payload);
    return NextResponse.json(response);
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Unknown selection persistence failure",
      },
      { status: 500 },
    );
  }
}
