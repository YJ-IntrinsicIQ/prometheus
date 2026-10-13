import { notFound } from "next/navigation";
import { AppFrame } from "@/src/components/layout/app-frame";
import { SpecialistPage } from "@/src/components/panel/panel-view";
import { loadPanel } from "@/src/lib/panel/load-panel";
import { specialistById } from "@/src/lib/panel/specialists";

export const dynamic = "force-dynamic";

export default async function SpecialistRoute({ params }: { params: Promise<{ companySlug: string; specialist: string }> }) {
  const { companySlug, specialist } = await params;
  if (!specialistById(specialist)) notFound();
  const panel = await loadPanel(companySlug);
  const s = panel?.specialists.find((x) => x.id === specialist);
  if (!panel || !s) notFound();
  return <AppFrame><SpecialistPage panel={panel} s={s} /></AppFrame>;
}
