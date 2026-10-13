import { notFound } from "next/navigation";
import { AppFrame } from "@/src/components/layout/app-frame";
import { PanelOverview } from "@/src/components/panel/panel-view";
import { loadPanel } from "@/src/lib/panel/load-panel";

export const dynamic = "force-dynamic";

export default async function PanelPage({ params }: { params: Promise<{ companySlug: string }> }) {
  const { companySlug } = await params;
  const panel = await loadPanel(companySlug);
  if (!panel) notFound();
  return <AppFrame><PanelOverview panel={panel} /></AppFrame>;
}
