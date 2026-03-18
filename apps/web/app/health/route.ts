import { NextResponse } from "next/server";
import { getWorkspaceUrls } from "@/src/lib/workspace-status";

export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json({
    status: "ok",
    ...getWorkspaceUrls(),
  });
}
