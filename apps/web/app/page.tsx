import { OperatorWorkspace } from "@/src/components/operator-workspace";
import { getWorkspaceStatus, getWorkspaceUrls } from "@/src/lib/workspace-status";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const initialStatus = await getWorkspaceStatus();
  const urls = getWorkspaceUrls();

  return <OperatorWorkspace initialStatus={initialStatus} runtimeUrl={urls.runtimeUrl} />;
}
