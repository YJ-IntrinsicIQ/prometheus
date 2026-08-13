import Link from "next/link";
import {
  AnswerPageShell,
  ReadingColumn,
  WideContentColumn,
} from "@/src/components/answer-page-shell";
import { backToQuestionsRoute, questionRoute } from "@/src/lib/routes";
import { BusinessJourneyTimeline } from "@/src/components/business-journey-timeline";
import { CustomerRoleBreakdown } from "@/src/components/customer-role-breakdown";
import { EvidenceDisclosure } from "@/src/components/evidence-disclosure";
import { FinancialVisualRenderer } from "@/src/components/financial-visual-renderer";
import { InvestorAnswerStack } from "@/src/components/investor-answer-stack";
import { cleanPublicList } from "@/src/lib/ask-intrinsiciq/presentation";
import { shouldShowInvestorInterpretation } from "@/src/lib/ask-intrinsiciq/question-types";
import { NextQuestions } from "@/src/components/next-questions";
import { ProductsServicesSection } from "@/src/components/products-services-section";
import { RevenueFlow } from "@/src/components/revenue-flow";
import { StructuredAnswerSections } from "@/src/components/structured-answer-sections";
import type { CompanyResearchView, ResearchAnswerCard } from "@/src/types";

type AnswerViewProps = {
  companySlug: string;
  company: CompanyResearchView;
  answer: ResearchAnswerCard;
};

export function AnswerView({ companySlug, company, answer }: AnswerViewProps) {
  const categoryLookup = new Map(
    company.categories.flatMap((category) =>
      category.questions.map((question) => [question.id, category.title] as const),
    ),
  );
  const nextQuestionHrefs = answer.nextQuestions.slice(0, 3).map((question) => ({
    id: question.id,
    questionId: question.questionId,
    title: question.title,
    shortLabel: question.shortLabel,
    href: questionRoute(companySlug, question.questionId),
    categoryTitle: categoryLookup.get(question.questionId),
  }));
  const backHref = backToQuestionsRoute(companySlug);
  const visualLookup = new Map(
    company.financialVisuals.map((visual) => [visual.id, visual]),
  );
  const relatedVisuals = answer.financialVisualRefs
    .map((visualId) => visualLookup.get(visualId))
    .filter((visual): visual is NonNullable<typeof visual> => Boolean(visual));
  const cleanedKeyPoints = (() => {
    const seen = new Set<string>();
    if (answer.interpretation) {
      cleanPublicList([answer.interpretation.conclusion], { seen, limit: 1 });
      cleanPublicList([answer.interpretation.whyItMatters], { seen, limit: 1 });
      cleanPublicList([answer.interpretation.economicMechanism], { seen, limit: 1 });
      cleanPublicList(answer.interpretation.whatChanged, { seen, limit: 3 });
      cleanPublicList(answer.interpretation.positiveEvidence, { seen, limit: 3 });
      cleanPublicList(answer.interpretation.negativeEvidence, { seen, limit: 3 });
      cleanPublicList(answer.interpretation.unresolved, { seen, limit: 3 });
      cleanPublicList(answer.interpretation.whatToWatch, { seen, limit: 3 });
    }
    if (answer.progression) {
      cleanPublicList([answer.progression.headline], { seen, limit: 1 });
      cleanPublicList([answer.progression.whatChanged], { seen, limit: 1 });
      cleanPublicList([answer.progression.whyItChanged], { seen, limit: 1 });
      cleanPublicList(answer.progression.latestEvidence, { seen, limit: 4 });
      cleanPublicList(answer.progression.unresolvedItems, { seen, limit: 4 });
    }
    return cleanPublicList(answer.keyPoints, { seen, limit: 4 });
  })();

  return (
    <AnswerPageShell>
      <ReadingColumn>
        <Link
          href={backHref}
          className="inline-flex items-center text-sm font-medium text-accent transition hover:opacity-80 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          ← Back to questions
        </Link>
        <p className="mt-5 text-[0.72rem] uppercase tracking-[0.1em] text-muted">
          Focused answer
        </p>
        <div className="mt-4 inline-flex rounded-full border border-border bg-[rgba(255,255,255,0.62)] px-3 py-1 text-[0.72rem] tracking-[0.01em] text-muted">
          {statusLabel(answer.answerStatus)}
        </div>
        <h1 className="mt-4 font-serif text-[2.1rem] leading-tight text-foreground md:text-[2.5rem] xl:text-[2.65rem]">
          {answer.title}
        </h1>
        {answer.interpretation && shouldShowInvestorInterpretation(answer.questionType) ? (
          <div className="mt-7">
            <InvestorAnswerStack answer={answer} />
          </div>
        ) : (
          <>
            <p className="mt-6 font-serif text-[1.3rem] leading-8 text-foreground md:text-[1.5rem] md:leading-9">
              {answer.simpleAnswer}
            </p>
            <p className="mt-4 text-[0.98rem] leading-7 text-muted">
              {answer.whyItMatters ?? answer.detailedExplanation}
            </p>
          </>
        )}

        <div className="mt-8 grid gap-3">
          {cleanedKeyPoints.map((point, index) => (
            <div
              key={`${answer.id}-point-${index}`}
              className="rounded-[22px] border border-border bg-[rgba(255,255,255,0.52)] px-5 py-4"
            >
              <p className="text-[0.95rem] leading-7 text-muted">{point}</p>
            </div>
          ))}
        </div>

        {answer.detailedExplanation &&
        answer.detailedExplanation !== answer.whyItMatters ? (
          <details className="group mt-6 rounded-[24px] border border-border bg-[rgba(255,255,255,0.42)] px-5 py-4">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3">
              <span className="text-[0.98rem] font-medium text-foreground">
                Read detailed explanation
              </span>
              <span className="text-[0.8rem] text-muted">
                <span className="group-open:hidden">Show</span>
                <span className="hidden group-open:inline">Hide</span>
              </span>
            </summary>
            <p className="mt-4 text-[0.95rem] leading-7 text-muted">
              {answer.detailedExplanation}
            </p>
          </details>
        ) : null}
      </ReadingColumn>

      <WideContentColumn>
        {answer.businessJourney ? (
          <BusinessJourneyTimeline journey={answer.businessJourney} />
        ) : null}
        {answer.customerRoles ? (
          <CustomerRoleBreakdown customerRoles={answer.customerRoles} />
        ) : null}
        {answer.revenueFlow ? <RevenueFlow revenueFlow={answer.revenueFlow} /> : null}
        {answer.productsAndServices.length > 0 && !answer.revenueFlow ? (
          <ProductsServicesSection groups={answer.productsAndServices} />
        ) : null}
        {answer.structuredSections && answer.structuredSections.length > 0 ? (
          <StructuredAnswerSections sections={answer.structuredSections} />
        ) : null}
        <FinancialVisualRenderer visuals={relatedVisuals} />
        {answer.uncertaintyNote.detail ? (
          <div className="rounded-[18px] border border-[rgba(100,116,139,0.18)] bg-[rgba(148,163,184,0.08)] px-4 py-3">
            <div className="flex items-start gap-2.5">
              <span className="mt-0.5 text-[0.95rem] text-muted">○</span>
              <div>
                <p className="text-[0.82rem] font-medium text-foreground">
                  {answer.uncertaintyNote.label}
                </p>
                <p className="mt-1 text-[0.9rem] leading-6 text-muted">
                  {answer.uncertaintyNote.detail}
                </p>
              </div>
            </div>
          </div>
        ) : null}

        <EvidenceDisclosure items={answer.evidenceSummary} />
        <NextQuestions questions={nextQuestionHrefs} exploreHref={backHref} />
        {company.sourceState.mode === "demo" ? (
          <p className="text-sm leading-6 text-muted">
            Development fixture only. Canonical Ask IntrinsicIQ output is not
            available in this environment yet.
          </p>
        ) : null}
      </WideContentColumn>
    </AnswerPageShell>
  );
}

function statusLabel(status: ResearchAnswerCard["answerStatus"]) {
  switch (status) {
    case "supported":
      return "Evidence supported";
    case "partially_supported":
      return "Partially supported";
    case "not_supported":
      return "Not supported by available evidence";
    case "unavailable":
      return "Unavailable in current release";
    default:
      return "Evidence supported";
  }
}
