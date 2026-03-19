import { NextRequest, NextResponse } from "next/server";
import { orchestrateSelectionRequest } from "@/src/lib/agent-api";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    const payload = await request.json();
    const response = await orchestrateSelectionRequest(payload);
    return NextResponse.json(response);
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Unknown orchestration failure",
      },
      { status: 500 },
    );
  }
}
