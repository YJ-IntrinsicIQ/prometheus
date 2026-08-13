import type {
  CompanyResearchView,
  ResearchAnswerCard,
} from "@/src/types";
import { getQuestionPresentationType } from "@/src/lib/ask-intrinsiciq/question-types";

const FALLBACK_QUESTIONS = [
  {
    id: "what-does-company-do",
    categoryId: "understand-the-business",
    title: "What does the company do?",
    shortLabel: "What it does",
    recommended: true,
    availabilityStatus: "unavailable" as const,
    answerCardId: "answer-what-does-company-do",
  },
  {
    id: "who-are-the-customers",
    categoryId: "understand-the-business",
    title: "Who are the customers?",
    shortLabel: "Customers",
    recommended: false,
    availabilityStatus: "unavailable" as const,
    answerCardId: "answer-who-are-the-customers",
  },
  {
    id: "how-does-it-make-money",
    categoryId: "understand-the-business",
    title: "How does it make money?",
    shortLabel: "Revenue model",
    recommended: false,
    availabilityStatus: "unavailable" as const,
    answerCardId: "answer-how-does-it-make-money",
  },
  {
    id: "what-makes-the-offering-important",
    categoryId: "understand-the-business",
    title: "What makes the offering important?",
    shortLabel: "Why it matters",
    recommended: false,
    availabilityStatus: "unavailable" as const,
    answerCardId: "answer-what-makes-the-offering-important",
  },
  {
    id: "where-is-evidence-thin",
    categoryId: "understand-the-business",
    title: "Where is evidence thin?",
    shortLabel: "Evidence gaps",
    recommended: false,
    availabilityStatus: "unavailable" as const,
    answerCardId: "answer-where-is-evidence-thin",
  },
  {
    id: "are-profits-converting-into-cash",
    categoryId: "financials",
    title: "Is profit converting into cash?",
    shortLabel: "Profit to cash",
    recommended: false,
    availabilityStatus: "unavailable" as const,
    answerCardId: "answer-are-profits-converting-into-cash",
  },
  {
    id: "what-is-owner-earnings",
    categoryId: "financials",
    title: "What is owner earnings?",
    shortLabel: "Owner earnings",
    recommended: false,
    availabilityStatus: "unavailable" as const,
    answerCardId: "answer-what-is-owner-earnings",
  },
  {
    id: "is-working-capital-a-concern",
    categoryId: "financials",
    title: "Is working capital a concern?",
    shortLabel: "Working capital",
    recommended: false,
    availabilityStatus: "unavailable" as const,
    answerCardId: "answer-is-working-capital-a-concern",
  },
  {
    id: "are-per-share-economics-improving",
    categoryId: "financials",
    title: "Are per-share economics improving?",
    shortLabel: "Per-share",
    recommended: false,
    availabilityStatus: "unavailable" as const,
    answerCardId: "answer-are-per-share-economics-improving",
  },
  {
    id: "which-financial-assumption-matters-most",
    categoryId: "financials",
    title: "Which financial assumption matters most?",
    shortLabel: "Key assumption",
    recommended: false,
    availabilityStatus: "unavailable" as const,
    answerCardId: "answer-which-financial-assumption-matters-most",
  },
  {
    id: "what-has-management-promised",
    categoryId: "management",
    title: "What has management promised?",
    shortLabel: "Promises",
    recommended: false,
    availabilityStatus: "unavailable" as const,
    answerCardId: "answer-what-has-management-promised",
  },
  {
    id: "did-past-claims-come-true",
    categoryId: "management",
    title: "Did past claims come true?",
    shortLabel: "Follow-through",
    recommended: false,
    availabilityStatus: "unavailable" as const,
    answerCardId: "answer-did-past-claims-come-true",
  },
  {
    id: "how-is-capital-allocated",
    categoryId: "management",
    title: "How is capital allocated?",
    shortLabel: "Capital allocation",
    recommended: false,
    availabilityStatus: "unavailable" as const,
    answerCardId: "answer-how-is-capital-allocated",
  },
  {
    id: "what-incentives-matter",
    categoryId: "management",
    title: "What incentives matter?",
    shortLabel: "Incentives",
    recommended: false,
    availabilityStatus: "unavailable" as const,
    answerCardId: "answer-what-incentives-matter",
  },
  {
    id: "what-should-i-ask-ir",
    categoryId: "management",
    title: "What should I ask IR?",
    shortLabel: "Ask IR",
    recommended: false,
    availabilityStatus: "unavailable" as const,
    answerCardId: "answer-what-should-i-ask-ir",
  },
  {
    id: "what-would-graham-worry-about",
    categoryId: "investor-panel",
    title: "What would Graham worry about?",
    shortLabel: "Graham",
    recommended: false,
    availabilityStatus: "unavailable" as const,
    answerCardId: "answer-what-would-graham-worry-about",
  },
  {
    id: "what-would-buffett-focus-on",
    categoryId: "investor-panel",
    title: "What would Buffett focus on?",
    shortLabel: "Buffett",
    recommended: true,
    availabilityStatus: "unavailable" as const,
    answerCardId: "answer-what-would-buffett-focus-on",
  },
  {
    id: "where-would-fisher-be-curious",
    categoryId: "investor-panel",
    title: "Where would Fisher be curious?",
    shortLabel: "Fisher",
    recommended: false,
    availabilityStatus: "unavailable" as const,
    answerCardId: "answer-where-would-fisher-be-curious",
  },
  {
    id: "what-would-munger-avoid",
    categoryId: "investor-panel",
    title: "What would Munger avoid?",
    shortLabel: "Munger",
    recommended: false,
    availabilityStatus: "unavailable" as const,
    answerCardId: "answer-what-would-munger-avoid",
  },
  {
    id: "how-would-lynch-explain-it",
    categoryId: "investor-panel",
    title: "How would Lynch explain it?",
    shortLabel: "Lynch",
    recommended: false,
    availabilityStatus: "unavailable" as const,
    answerCardId: "answer-how-would-lynch-explain-it",
  },
  {
    id: "what-can-break-the-thesis",
    categoryId: "risks-and-diligence",
    title: "What can break the thesis?",
    shortLabel: "Break the thesis",
    recommended: false,
    availabilityStatus: "unavailable" as const,
    answerCardId: "answer-what-can-break-the-thesis",
  },
  {
    id: "which-disclosure-is-missing",
    categoryId: "risks-and-diligence",
    title: "Which disclosure is missing?",
    shortLabel: "Missing disclosure",
    recommended: false,
    availabilityStatus: "unavailable" as const,
    answerCardId: "answer-which-disclosure-is-missing",
  },
  {
    id: "what-evidence-would-change-the-view",
    categoryId: "risks-and-diligence",
    title: "What evidence would change the view?",
    shortLabel: "Change the view",
    recommended: false,
    availabilityStatus: "unavailable" as const,
    answerCardId: "answer-what-evidence-would-change-the-view",
  },
  {
    id: "what-needs-management-clarification",
    categoryId: "risks-and-diligence",
    title: "What needs management clarification?",
    shortLabel: "Needs clarification",
    recommended: false,
    availabilityStatus: "unavailable" as const,
    answerCardId: "answer-what-needs-management-clarification",
  },
  {
    id: "what-remains-unresolved",
    categoryId: "risks-and-diligence",
    title: "What remains unresolved?",
    shortLabel: "Unresolved",
    recommended: false,
    availabilityStatus: "unavailable" as const,
    answerCardId: "answer-what-remains-unresolved",
  },
];

export function getDevelopmentFixtureCompanySlugs() {
  return ["datapatterns"];
}

export function getDevelopmentLandingCompanies() {
  return [
    {
      slug: "datapatterns",
      name: "Data Patterns (India) Limited",
    },
  ];
}

export function buildDevelopmentCompanyResearchView(
  companySlug: string,
): CompanyResearchView | null {
  if (!getDevelopmentFixtureCompanySlugs().includes(companySlug)) {
    return null;
  }

  return {
    schemaVersion: "ask_intrinsiciq.company_research_view.v1",
    company: {
      companySlug,
      companyName: "Data Patterns (India) Limited",
      displayName: "Data Patterns (India) Limited",
      reportingPeriodsCovered: ["FY24"],
      primaryIndustry: "Defence and aerospace electronics",
      shortDescription:
        "This development fixture is only used when canonical Ask IntrinsicIQ output is unavailable locally.",
    },
    coverage: {
      availableCategoryIds: [
        "understand-the-business",
        "financials",
        "management",
        "investor-panel",
        "risks-and-diligence",
      ],
      sourcedAnswerCount: 0,
      partiallySupportedAnswerCount: 0,
      unsupportedAnswerCount: 0,
      unavailableAnswerCount: FALLBACK_QUESTIONS.length,
      evidenceStatus: "missing",
      summary:
        "Canonical Ask IntrinsicIQ output is not available in this local development environment yet.",
    },
    categories: [
      {
        id: "understand-the-business",
        title: "Understand the Business",
        shortDescription:
          "Start with the plain-language business model, customers, and the few details that make the company important.",
        displayOrder: 1,
        questions: FALLBACK_QUESTIONS.filter(
          (question) => question.categoryId === "understand-the-business",
        ),
      },
      {
        id: "financials",
        title: "Financials",
        shortDescription:
          "Keep the financial reading compact, careful, and investor-readable rather than dashboard-heavy.",
        displayOrder: 2,
        questions: FALLBACK_QUESTIONS.filter(
          (question) => question.categoryId === "financials",
        ),
      },
      {
        id: "management",
        title: "Management",
        shortDescription:
          "Look at promises, execution, capital allocation, and the questions a careful reader would want answered.",
        displayOrder: 3,
        questions: FALLBACK_QUESTIONS.filter(
          (question) => question.categoryId === "management",
        ),
      },
      {
        id: "investor-panel",
        title: "Investor Panel",
        shortDescription:
          "Use investor-style lenses as curated instructions, not as a dashboard or permanent switcher.",
        displayOrder: 4,
        questions: FALLBACK_QUESTIONS.filter(
          (question) => question.categoryId === "investor-panel",
        ),
      },
      {
        id: "risks-and-diligence",
        title: "Risks and Diligence",
        shortDescription:
          "Keep the unresolved issues visible so the next step stays grounded instead of overconfident.",
        displayOrder: 5,
        questions: FALLBACK_QUESTIONS.filter(
          (question) => question.categoryId === "risks-and-diligence",
        ),
      },
    ],
    businessJourney: null,
    productsAndServices: [],
    financialVisuals: [],
    generatedAt: new Date("2026-08-02T00:00:00.000Z").toISOString(),
    sourceState: {
      producer: "prometheus",
      mode: "demo",
      contentStatus: "unavailable",
      sourceMode: "development_fixture",
      summary:
        "Canonical Ask IntrinsicIQ output is missing, so a local development fixture is being shown instead.",
      notes: [
        "Development fixture only. Real company output has not been loaded.",
      ],
    },
  };
}

export function buildDevelopmentAnswerCard(
  companySlug: string,
  questionId: string,
): ResearchAnswerCard | null {
  const company = buildDevelopmentCompanyResearchView(companySlug);
  const question = company?.categories
    .flatMap((category) => category.questions)
    .find((entry) => entry.id === questionId);

  if (!company || !question) {
    return null;
  }

  const nextQuestions = company.categories
    .flatMap((category) => category.questions)
    .filter((entry) => entry.id !== questionId)
    .slice(0, 3)
    .map((entry) => ({
      id: entry.id,
      questionId: entry.id,
      title: entry.title,
      shortLabel: entry.shortLabel,
    })) as [ResearchAnswerCard["nextQuestions"][0], ResearchAnswerCard["nextQuestions"][1], ResearchAnswerCard["nextQuestions"][2]];

  return {
    id: question.answerCardId,
    questionId: question.id,
    title: question.title,
    simpleAnswer:
      "This answer is not available because canonical Ask IntrinsicIQ output is missing in this local development environment.",
    whyItMatters:
      "The screen remains wired up so the UI can be tested without mixing synthetic copy into live company intelligence.",
    keyPoints: [
      "No canonical backend output was found for this company in the local repository.",
      "The route still resolves so navigation, spacing, and empty-state behavior remain testable.",
    ],
    detailedExplanation:
      "This development fixture exists only to keep the renderer stable while canonical Ask IntrinsicIQ files are absent. Once the backend output directory is present, the frontend should load only those canonical files.",
    productsAndServices: [],
    businessJourney: null,
    financialVisualRefs: [],
    evidenceSummary: [
      {
        label: "Development fixture",
        detail:
          "No canonical Ask IntrinsicIQ output was found for this route in the local environment.",
        evidenceStatus: "missing",
      },
    ],
    uncertaintyNote: {
      label: "Availability note",
      detail:
        "A local fixture is being shown because canonical output is missing.",
      evidenceStatus: "missing",
    },
    nextQuestions,
    answerStatus: "unavailable",
    questionType: getQuestionPresentationType(questionId),
    generatedAt: company.generatedAt,
  };
}
