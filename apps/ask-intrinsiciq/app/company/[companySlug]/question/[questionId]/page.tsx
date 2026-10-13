import { notFound, redirect } from "next/navigation";
import { AppFrame } from "@/src/components/layout/app-frame";
import { QuestionExperience, QuestionPending } from "@/src/components/story/question-experience";
import { findQuestion, loadCatalog } from "@/src/lib/catalog/catalog";
import { availableAnnualReports } from "@/src/lib/evidence/documents";
import { questionRoute } from "@/src/lib/routes";
import { relatedFor } from "@/src/lib/catalog/journey";
import { loadExplorer } from "@/src/lib/catalog/load-explorer";
import { approvedQuestionIds } from "@/src/lib/story/authorization";
import { COMPANIES } from "@/src/lib/story/companies";
import { loadQuestionView } from "@/src/lib/story/load-question";
import { QUESTIONS } from "@/src/lib/story/questions";

export const dynamic = "force-dynamic";

// One page for every catalog question. An approved answer is shown by the shared renderer; a catalog question without
// one says so. A question that is not in the catalog is a 404.
export default async function QuestionPage({ params }: { params: Promise<{ companySlug: string; questionId: string }> }) {
  const { companySlug, questionId } = await params;
  const company = COMPANIES[companySlug];
  if (!company) notFound();
  const catalog = await loadCatalog();
  const hit = findQuestion(catalog, questionId);
  if (!hit) notFound();
  // A catalog question served by a certified question lives at the certified question's address.
  if (!hit.viaCertified && hit.q.certifiedId && hit.q.certifiedId !== questionId) redirect(questionRoute(companySlug, hit.q.certifiedId));
  const view = await loadQuestionView(companySlug, questionId); // null unless the approval gate passes for THIS company
  if (view) return <AppFrame><QuestionExperience view={view} /></AppFrame>;
  const available = await approvedQuestionIds(companySlug);
  const family = catalog.families.find((f) => f.id === hit.q.family);
  const title = QUESTIONS.find((q) => q.id === questionId)?.title ?? hit.q.title;
  const explorer = await loadExplorer(companySlug);   // titles of the approved questions only
  const related = relatedFor(catalog, available, companySlug, hit.q.id, 5);
  return (
    <AppFrame>
      <QuestionPending slug={companySlug} company={company.name} available={available} docs={availableAnnualReports(companySlug)} titles={explorer?.titles} question={{ id: questionId, title }} familyTitle={family?.title ?? ""} familyId={hit.q.family} entry={hit.q} related={related} />
    </AppFrame>
  );
}
