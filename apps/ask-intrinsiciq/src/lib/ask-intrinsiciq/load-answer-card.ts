import type {
  BusinessJourney,
  ProductServiceGroup,
  ResearchAnswerCard,
} from "@/src/types";
import type { InvestorInterpretation } from "@/src/types/investor-interpretation";
import type { ProgressionInsight } from "@/src/types/progression";
import type { QuestionPresentationType } from "@/src/types/question-presentation";
import { readJsonIfExists } from "@/src/lib/prometheus/read-json";
import { buildUnavailableResearchAnswerCard } from "@/src/lib/ask-intrinsiciq/company-discovery";
import {
  finalizeResearchAnswerCardForDisplay,
  cleanPublicList,
  cleanPublicText,
} from "@/src/lib/ask-intrinsiciq/presentation";
import { getQuestionPresentationType } from "@/src/lib/ask-intrinsiciq/question-types";
import {
  getCompanyResearchView,
  getFinancialVisuals,
  getProductsServices,
} from "@/src/lib/ask-intrinsiciq/load-company-research-view";
import {
  getAskIntrinsicIqPaths,
  isValidRouteSegment,
} from "@/src/lib/ask-intrinsiciq/paths";
import { validateResearchAnswerCard } from "@/src/lib/ask-intrinsiciq/validate-runtime-view";

type RawAnswerCardsPayload = {
  company_slug?: string;
  answers: Array<{
    id: string;
    question_id: string;
    title: string;
    simple_answer: string;
    why_it_matters?: string | null;
    key_points: string[];
    detailed_explanation: string;
    products_and_services_refs: string[];
    business_journey_ref?: string | null;
    business_journey_mode?: "none" | "summary" | "full" | null;
    financial_visual_refs: string[];
    customer_roles?: {
      payers: string[];
      integrators_or_partners: string[];
      end_users: string[];
      international_customers: string[];
      concentration_note: string;
      evidence_status: ResearchAnswerCard["uncertaintyNote"]["evidenceStatus"];
    } | null;
    revenue_flow?: {
      model_type: "project_based" | "recurring" | "mixed" | "unclear";
      steps: Array<
        | {
            order: number;
            label: string;
            explanation: string;
          }
        | string
      >;
      billing_basis_note?: string | null;
      revenue_recognition_note?: string | null;
      cash_timing_note?: string | null;
      working_capital_note?: string | null;
      evidence_status: ResearchAnswerCard["uncertaintyNote"]["evidenceStatus"];
      offering_examples?: string[];
    } | null;
    structured_sections?: Array<{
      title: string;
      points: string[];
    }>;
    progression?: ProgressionInsight | null;
    question_type?: string | null;
    interpretation?: {
      conclusion?: string | null;
      what_changed?: string[];
      why_it_matters?: string | null;
      economic_mechanism?: string | null;
      thesis_impact?: InvestorInterpretation["thesisImpact"] | null;
      positive_evidence?: string[];
      negative_evidence?: string[];
      unresolved?: string[];
      what_to_watch?: string[];
      confidence?: {
        level?: InvestorInterpretation["confidence"]["level"] | null;
        basis?: string[];
        limitations?: string[];
      } | null;
    } | null;
    evidence_summary: {
      status: ResearchAnswerCard["evidenceSummary"][number]["evidenceStatus"];
      summary: string;
      supporting_points: string[];
    };
    uncertainty_note: {
      title: string;
      message: string;
    };
    next_questions: Array<{
      category_id: string;
      question_id: string;
      title: string;
    }>;
    answer_status: ResearchAnswerCard["answerStatus"];
    generated_at: string;
  }>;
};

function logRuntimeIssue(message: string, detail?: unknown) {
  console.error(`[Ask IntrinsicIQ] ${message}`, detail);
}

function artifactCompanyMatches(
  companySlug: string,
  artifactCompanySlug: string | null | undefined,
  artifactPath: string,
) {
  if (!artifactCompanySlug || artifactCompanySlug === companySlug) {
    return true;
  }

  logRuntimeIssue("Company-scoped answer artifact rejected because company identity mismatched.", {
    failure_class: "CROSS_COMPANY_INTELLIGENCE_CONTAMINATION",
    requested_company: companySlug,
    artifact_company: artifactCompanySlug,
    artifact_path: artifactPath,
  });
  return false;
}

function groupReferencedProducts(
  allGroups: ProductServiceGroup[] | null,
  refs: string[],
): ProductServiceGroup[] {
  if (!allGroups || refs.length === 0) {
    return [];
  }

  const refSet = new Set(refs);

  return allGroups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => refSet.has(item.id)),
    }))
    .filter((group) => group.items.length > 0);
}

function normalizeRevenueFlowStep(
  step: RawAnswerCardsPayload["answers"][number]["revenue_flow"] extends infer RevenueFlow
    ? RevenueFlow extends { steps: Array<infer Step> }
      ? Step
      : never
    : never,
  index: number,
) {
  if (typeof step === "string") {
    return {
      order: index + 1,
      label: step,
      explanation: "",
    };
  }

  return {
    order: step.order,
    label: step.label,
    explanation: step.explanation,
  };
}

function getJourneyForAnswer(
  journey: BusinessJourney | null | undefined,
  mode?: "none" | "summary" | "full" | null,
  stageId?: string | null,
): BusinessJourney | null {
  if (!journey) {
    return null;
  }

  if (mode === "none" || (!mode && !stageId)) {
    return null;
  }

  if (mode === "full") {
    return journey;
  }

  const stage = journey.stages.find((entry) => entry.id === stageId);

  if (!stage) {
    return mode === "summary" ? null : journey;
  }

  return {
    ...journey,
    stages: [stage],
  };
}

function mapInterpretation(
  raw: RawAnswerCardsPayload["answers"][number]["interpretation"],
): InvestorInterpretation | null {
  if (!raw) {
    return null;
  }

  const sharedSeen = new Set<string>();
  const conclusion = cleanPublicText(raw.conclusion ?? "");
  const economicMechanism = cleanPublicText(raw.economic_mechanism ?? "");
  const whyItMatters = cleanPublicText(raw.why_it_matters ?? "");
  if (!conclusion && !economicMechanism && !whyItMatters) {
    return null;
  }

  if (conclusion) {
    cleanPublicList([conclusion], { seen: sharedSeen, limit: 1 });
  }
  if (whyItMatters) {
    cleanPublicList([whyItMatters], { seen: sharedSeen, limit: 1 });
  }
  if (economicMechanism) {
    cleanPublicList([economicMechanism], { seen: sharedSeen, limit: 1 });
  }

  return {
    conclusion: conclusion ?? "",
    whatChanged: cleanPublicList(raw.what_changed ?? [], { seen: sharedSeen, limit: 3 }),
    whyItMatters: whyItMatters ?? "",
    economicMechanism: economicMechanism ?? "",
    thesisImpact: raw.thesis_impact ?? "unresolved",
    positiveEvidence: cleanPublicList(raw.positive_evidence ?? [], { seen: sharedSeen, limit: 3 }),
    negativeEvidence: cleanPublicList(raw.negative_evidence ?? [], { seen: sharedSeen, limit: 3 }),
    unresolved: cleanPublicList(raw.unresolved ?? [], { seen: sharedSeen, limit: 3 }),
    whatToWatch: cleanPublicList(raw.what_to_watch ?? [], { seen: sharedSeen, limit: 3 }),
    confidence: {
      level: raw.confidence?.level ?? "medium",
      basis: cleanPublicList(raw.confidence?.basis ?? [], { limit: 2 }),
      limitations: cleanPublicList(raw.confidence?.limitations ?? [], { limit: 2 }),
    },
  };
}

async function loadCanonicalAnswerCard(
  companySlug: string,
  questionId: string,
): Promise<ResearchAnswerCard | null> {
  const paths = getAskIntrinsicIqPaths(companySlug);

  if (!paths) {
    return null;
  }

  const [payload, company, productsAndServices, financialVisuals] =
    await Promise.all([
      readJsonIfExists<RawAnswerCardsPayload>(paths.answerCards),
      getCompanyResearchView(companySlug),
      getProductsServices(companySlug),
      getFinancialVisuals(companySlug),
    ]);

  const raw = payload?.answers.find((entry) => entry.question_id === questionId);

  if (!raw || !company || !artifactCompanyMatches(companySlug, payload?.company_slug, paths.answerCards)) {
    return null;
  }

  const nextQuestions = raw.next_questions.slice(0, 3).map((entry) => {
    const matchingQuestion = company.categories
      .flatMap((category) => category.questions)
      .find((question) => question.id === entry.question_id);

    return {
      id: entry.question_id,
      questionId: entry.question_id,
      title: entry.title,
      shortLabel: matchingQuestion?.shortLabel ?? entry.title,
    };
  });

  if (nextQuestions.length !== 3) {
    logRuntimeIssue("Canonical answer card did not contain exactly three next questions.", {
      companySlug,
      questionId,
      nextQuestions,
    });
    return null;
  }

  const card: ResearchAnswerCard = {
    id: raw.id,
    questionId: raw.question_id,
    title: raw.title,
    simpleAnswer: raw.simple_answer,
    whyItMatters: raw.why_it_matters ?? null,
    keyPoints: raw.key_points.slice(0, 4),
    detailedExplanation: raw.detailed_explanation,
    productsAndServices: groupReferencedProducts(
      productsAndServices,
      raw.products_and_services_refs,
    ),
    businessJourney: getJourneyForAnswer(
      company.businessJourney,
      raw.business_journey_mode,
      raw.business_journey_ref,
    ),
    financialVisualRefs: raw.financial_visual_refs.filter((visualId) =>
      financialVisuals.some((visual) => visual.id === visualId),
    ),
    customerRoles: raw.customer_roles
      ? {
          payers: raw.customer_roles.payers ?? [],
          integratorsOrPartners: raw.customer_roles.integrators_or_partners ?? [],
          endUsers: raw.customer_roles.end_users ?? [],
          internationalCustomers: raw.customer_roles.international_customers ?? [],
          concentrationNote: raw.customer_roles.concentration_note ?? "",
          evidenceStatus: raw.customer_roles.evidence_status ?? "partial",
        }
      : null,
    revenueFlow: raw.revenue_flow
      ? {
          modelType: raw.revenue_flow.model_type,
          steps: (raw.revenue_flow.steps ?? [])
            .slice(0, 6)
            .map((step, index) => normalizeRevenueFlowStep(step, index)),
          billingBasisNote: raw.revenue_flow.billing_basis_note ?? undefined,
          revenueRecognitionNote: raw.revenue_flow.revenue_recognition_note ?? undefined,
          cashTimingNote: raw.revenue_flow.cash_timing_note ?? undefined,
          workingCapitalNote: raw.revenue_flow.working_capital_note ?? undefined,
          evidenceStatus: raw.revenue_flow.evidence_status ?? "partial",
          offeringExamples: raw.revenue_flow.offering_examples ?? [],
        }
      : null,
    structuredSections: (() => {
      const sharedSeen = new Set<string>();
      const sections = (raw.structured_sections ?? [])
        .map((section) => {
          const title = cleanPublicText(section.title ?? "");
          const points = cleanPublicList(section.points ?? [], { seen: sharedSeen, limit: 3 });
          return {
            title,
            points,
          };
        })
        .filter((section) => section.title && section.points.length > 0);
      return sections;
    })(),
    questionType: (raw.question_type as QuestionPresentationType | null) ?? getQuestionPresentationType(questionId),
    progression: raw.progression
      ? {
          headline: cleanPublicText(raw.progression.headline ?? ""),
          currentState: cleanPublicText(raw.progression.currentState ?? ""),
          whatChanged: cleanPublicText(raw.progression.whatChanged ?? ""),
          whyItChanged: cleanPublicText(raw.progression.whyItChanged ?? ""),
          convictionImpact: raw.progression.convictionImpact ?? "unclear",
          latestEvidence: cleanPublicList(raw.progression.latestEvidence ?? [], { limit: 4 }),
          unresolvedItems: cleanPublicList(raw.progression.unresolvedItems ?? [], { limit: 4 }),
          turningPoints: (raw.progression.turningPoints ?? [])
            .map((point) => ({
              period: cleanPublicText(point.period ?? ""),
              label: cleanPublicText(point.label ?? ""),
              description: cleanPublicText(point.description ?? ""),
              whyItMatters: cleanPublicText(point.whyItMatters ?? ""),
              impact: point.impact ?? "unclear",
            }))
            .filter((point) => point.label || point.description),
        }
      : null,
    interpretation: mapInterpretation(raw.interpretation ?? null),
    evidenceSummary: [
      {
        label: "Evidence summary",
        detail: cleanPublicText(raw.evidence_summary.summary ?? ""),
        evidenceStatus: raw.evidence_summary.status,
      },
      ...cleanPublicList(raw.evidence_summary.supporting_points, { limit: 3 }).map((detail, index) => ({
        label: `Supporting point ${index + 1}`,
        detail,
        evidenceStatus: raw.evidence_summary.status,
      })),
    ].filter((item) => item.detail),
    uncertaintyNote: {
      label: cleanPublicText(raw.uncertainty_note.title ?? ""),
      detail: cleanPublicText(raw.uncertainty_note.message ?? ""),
      evidenceStatus: "partial",
    },
    nextQuestions: nextQuestions as ResearchAnswerCard["nextQuestions"],
    answerStatus: raw.answer_status,
    generatedAt: raw.generated_at,
  };

  const finalized = finalizeResearchAnswerCardForDisplay(card);

  const errors = validateResearchAnswerCard(finalized);

  if (errors.length > 0) {
    logRuntimeIssue("Canonical answer card failed runtime validation.", {
      companySlug,
      questionId,
      errors,
    });
    return null;
  }

  return finalized;
}

export async function getResearchAnswerCard(
  companySlug: string,
  questionId: string,
): Promise<ResearchAnswerCard | null> {
  if (!isValidRouteSegment(companySlug) || !isValidRouteSegment(questionId)) {
    return null;
  }

  const [answer, company] = await Promise.all([
    loadCanonicalAnswerCard(companySlug, questionId),
    getCompanyResearchView(companySlug),
  ]);

  if (answer) {
    return answer;
  }

  if (company) {
    return buildUnavailableResearchAnswerCard(companySlug, questionId, company);
  }

  return null;
}

export async function getResearchQuestionParams() {
  const companySlugs = await import("@/src/lib/ask-intrinsiciq/load-company-research-view").then(
    (module) => module.getCompanySlugs(),
  );
  const companies = await Promise.all(
    companySlugs.map((companySlug) => getCompanyResearchView(companySlug)),
  );

  return companies.flatMap((company) =>
    company
      ? company.categories.flatMap((category) =>
          category.questions.map((question) => ({
            companySlug: company.company.companySlug,
            questionId: question.id,
          })),
        )
      : [],
  );
}
