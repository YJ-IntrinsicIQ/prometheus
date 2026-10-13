import { notFound } from "next/navigation";
import { AppFrame } from "@/src/components/layout/app-frame";
import { QuestionExplorer } from "@/src/components/catalog/question-explorer";
import { loadExplorer } from "@/src/lib/catalog/load-explorer";

export const dynamic = "force-dynamic";

export default async function QuestionsPage({ params }: { params: Promise<{ companySlug: string }> }) {
  const { companySlug } = await params;
  const data = await loadExplorer(companySlug);
  if (!data) notFound();
  return <AppFrame><QuestionExplorer data={data} /></AppFrame>;
}
