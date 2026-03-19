import { NextResponse } from "next/server";
import { getWorkspaceStatus, getWorkspaceUrls } from "@/src/lib/workspace-status";

export const dynamic = "force-dynamic";

export async function GET() {
  const status = await getWorkspaceStatus();
  return NextResponse.json({
    ...status,
    urls: getWorkspaceUrls(),
  });
}
