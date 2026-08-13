import path from "node:path";
import { readdir } from "node:fs/promises";
import type {
  CompanyResearchView,
  ResearchAnswerCard,
  ResearchCategory,
} from "@/src/types";
import { readJsonIfExists } from "@/src/lib/prometheus/read-json";
import { getAskIntrinsicIqPaths, getRepoRoot } from "@/src/lib/ask-intrinsiciq/paths";
import { getQuestionPresentationType } from "@/src/lib/ask-intrinsiciq/question-types";

export type CompanyAvailabilityState = "READY" | "PARTIAL" | "UNAVAILABLE";

export type CompanyDiscoverySummary = {
  slug: string;
  name: string;
  availabilityState: CompanyAvailabilityState;
  reportingPeriods: string[];
  primaryIndustry: string;
  summary: string;
  importantUnknown: string;
  questionIds: string[];
};

type RawCompanyMemoryIndex = {
  company?: string;
  ordered_years?: string[];
  usable_years?: string[];
  incomplete_years?: Array<{
    year: string;
    status?: string;
    reason?: string;
  }>;
  discovered_years?: string[];
};

type RawYearlyIntelligenceIndex = {
  company?: string;
  years?: Array<{
    year: string;
    sort_key?: number;
    status?: string;
    reason?: string;
    paths?: {
      year_root?: string;
      intelligence_dir?: string;
    };
  }>;
};

type RawCompanyIntelligence = {
  metadata?: {
    company?: string;
    year?: string;
  };
  business?: {
    industry_profile?: {
      business_summary?: string;
      business_model?: string;
    };
  };
  management?: {
    summary?: Record<string, unknown>;
  };
  risk?: {
    identified?: {
      summary?: Record<string, unknown>;
    };
  };
};

const FallbackQuestions = [
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

type FallbackQuestion = (typeof FallbackQuestions)[number];

function readCompanyMemoryIndexPath(companySlug: string) {
  return path.join(getRepoRoot(), "companies", companySlug, "company_memory", "company_memory_index.json");
}

function readYearlyIntelligenceIndexPath(companySlug: string) {
  return path.join(getRepoRoot(), "companies", companySlug, "company_memory", "yearly_intelligence_index.json");
}

function readYearIntelligencePath(companySlug: string, year: string) {
  return path.join(getRepoRoot(), "companies", companySlug, year, "intelligence", "company_intelligence.json");
}

function slugToDisplayName(slug: string, fallback = slug) {
  return fallback
    .split("-")
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}

function extractDisplayNameFromSummary(summary: string, fallbackSlug: string) {
  const text = String(summary || "").trim();
  const match = text.match(/^([A-Z][A-Za-z0-9.&'/-]*(?:\s+[A-Z][A-Za-z0-9.&'/-]*){0,4})\s+(?:is|operates|creates|builds|provides|focuses|manufactures)\b/);
  return match?.[1]?.trim() || slugToDisplayName(fallbackSlug);
}

function extractPrimaryIndustry(summary: string, fallbackSlug: string) {
  const text = String(summary || "").trim();
  if (!text) {
    return slugToDisplayName(fallbackSlug);
  }
  const afterIs = text.match(/^\s*[A-Z][A-Za-z0-9.&'/-]*(?:\s+[A-Z][A-Za-z0-9.&'/-]*)*\s+is\s+(?:an?\s+)?([^.;]+?)(?:\s+with\b|,\s*|;|\.|$)/i);
  if (afterIs?.[1]) {
    return afterIs[1].trim();
  }
  const afterOperates = text.match(/^\s*[A-Z][A-Za-z0-9.&'/-]*(?:\s+[A-Z][A-Za-z0-9.&'/-]*)*\s+operates\s+([^.;]+?)(?:\s+with\b|,\s*|;|\.|$)/i);
  if (afterOperates?.[1]) {
    return afterOperates[1].trim();
  }
  return text.split(".")[0].trim();
}

function yearsToRange(years: string[]) {
  const normalized = years.filter(Boolean);
  if (normalized.length === 0) {
    return [];
  }
  return normalized.map((year) => year.toUpperCase());
}

function getFallbackCategories(): ResearchCategory[] {
  const categories = [
    {
      id: "understand-the-business",
      title: "Understand the Business",
      shortDescription:
        "Start with the plain-language business model, customers, and the few details that make the company important.",
      displayOrder: 1,
    },
    {
      id: "financials",
      title: "Financials",
      shortDescription:
        "Keep the financial reading compact, careful, and investor-readable rather than dashboard-heavy.",
      displayOrder: 2,
    },
    {
      id: "management",
      title: "Management",
      shortDescription:
        "Look at promises, execution, capital allocation, and the questions a careful reader would want answered.",
      displayOrder: 3,
    },
    {
      id: "investor-panel",
      title: "Investor Panel",
      shortDescription:
        "Use investor-style lenses as curated instructions, not as a dashboard or permanent switcher.",
      displayOrder: 4,
    },
    {
      id: "risks-and-diligence",
      title: "Risks and Diligence",
      shortDescription:
        "Keep the unresolved issues visible so the next step stays grounded instead of overconfident.",
      displayOrder: 5,
    },
  ];

  return categories.map((category) => ({
    ...category,
    questions: FallbackQuestions.filter((question) => question.categoryId === category.id),
  }));
}

async function loadCompanyIntelligence(companySlug: string, yearlyIndex?: RawYearlyIntelligenceIndex | null) {
  const sortedYears =
    yearlyIndex?.years
      ?.slice()
      .sort((left, right) => (left.sort_key ?? 0) - (right.sort_key ?? 0)) ?? [];
  const usableYears = sortedYears.filter((year) => year.status === "usable");
  const latestUsable = usableYears[usableYears.length - 1];
  if (!latestUsable?.year) {
    return null;
  }

  return readJsonIfExists<RawCompanyIntelligence>(readYearIntelligencePath(companySlug, latestUsable.year));
}

function buildUncertaintySummary(
  companySlug: string,
  memoryIndex: RawCompanyMemoryIndex | null,
  yearlyIndex: RawYearlyIntelligenceIndex | null,
  canonicalAvailable: boolean,
): NonNullable<CompanyResearchView["sourceState"]["uncertaintySummary"]> {
  const incompleteYears = memoryIndex?.incomplete_years ?? [];
  const latestMissing = incompleteYears[0];
  const latestUsableYear =
    yearlyIndex?.years?.slice().reverse().find((year) => year.status === "usable")?.year ?? null;

  if (canonicalAvailable) {
    return {
      importantUnknownsCount: 0,
      highSeverityCount: 0,
      mainUncertainty: "Canonical Ask IntrinsicIQ output is available for this company.",
      unresolvedQuestionCount: 0,
    };
  }

  if (latestMissing) {
    return {
      importantUnknownsCount: incompleteYears.length,
      highSeverityCount: 0,
      mainUncertainty: `${latestMissing.year.toUpperCase()} is still missing usable intelligence artifacts${latestMissing.reason ? `: ${latestMissing.reason}` : "."}`,
      unresolvedQuestionCount: incompleteYears.length,
    };
  }

  return {
    importantUnknownsCount: 1,
    highSeverityCount: 0,
    mainUncertainty: latestUsableYear
      ? `Ask IntrinsicIQ answer cards are not yet available for ${companySlug} even though company-memory intelligence exists through ${latestUsableYear.toUpperCase()}.`
      : `Ask IntrinsicIQ answer cards are not yet available for ${companySlug}.`,
    unresolvedQuestionCount: 1,
  };
}

async function loadCompanyMemoryIndex(companySlug: string) {
  return readJsonIfExists<RawCompanyMemoryIndex>(readCompanyMemoryIndexPath(companySlug));
}

async function loadYearlyIntelligenceIndex(companySlug: string) {
  return readJsonIfExists<RawYearlyIntelligenceIndex>(readYearlyIntelligenceIndexPath(companySlug));
}

export async function getDiscoveredCompanySlugs() {
  const companiesRoot = path.join(getRepoRoot(), "companies");
  try {
    const entries = await readdir(companiesRoot, { withFileTypes: true });
    const slugs = entries
      .filter((entry) => entry.isDirectory())
      .map((entry) => entry.name)
      .filter((slug) => /^[-a-z0-9]+$/.test(slug));
    const discovered = await Promise.all(
      slugs.map(async (slug) => {
        const index = await loadCompanyMemoryIndex(slug);
        return index ? slug : null;
      }),
    );
    return discovered.filter((slug): slug is string => Boolean(slug));
  } catch {
    return [];
  }
}

export async function getCompanyDiscoverySummaries(): Promise<CompanyDiscoverySummary[]> {
  const slugs = await getDiscoveredCompanySlugs();
  const companies = await Promise.all(slugs.map((slug) => getCompanyDiscoverySummary(slug)));
  return companies.filter((company): company is CompanyDiscoverySummary => Boolean(company));
}

export async function getCompanyDiscoverySummary(companySlug: string): Promise<CompanyDiscoverySummary | null> {
  const memoryIndex = await loadCompanyMemoryIndex(companySlug);
  if (!memoryIndex) {
    return null;
  }

  const yearlyIndex = await loadYearlyIntelligenceIndex(companySlug);
  const askPaths = getAskIntrinsicIqPaths(companySlug);
  const canonicalView = askPaths
    ? await readJsonIfExists<CompanyResearchView>(askPaths.companyResearchView)
    : null;
  const validationReport = askPaths
    ? await readJsonIfExists<{ status?: string }>(askPaths.validationReport)
    : null;
  const canonicalAvailable = Boolean(
    canonicalView &&
      validationReport?.status !== "fail" &&
      canonicalView.company?.companySlug === companySlug,
  );

  const companyIntelligence = await loadCompanyIntelligence(companySlug, yearlyIndex);
  const summaryText = String(companyIntelligence?.business?.industry_profile?.business_summary ?? "").trim();
  const displayName = canonicalAvailable
    ? canonicalView?.company.displayName ?? canonicalView?.company.companyName ?? companySlug
    : extractDisplayNameFromSummary(summaryText, companySlug);
  const primaryIndustry = canonicalAvailable
    ? canonicalView?.company.primaryIndustry ?? "Company-memory intelligence"
    : extractPrimaryIndustry(summaryText, companySlug);
  const usableYears = yearsToRange(memoryIndex.usable_years ?? []);
  const availabilityState: CompanyAvailabilityState = canonicalAvailable
    ? "READY"
    : usableYears.length > 0
      ? "PARTIAL"
      : "UNAVAILABLE";
  const questionIds = FallbackQuestions.map((question) => question.id);
  const importantUnknown = buildUncertaintySummary(companySlug, memoryIndex, yearlyIndex, canonicalAvailable).mainUncertainty;

  return {
    slug: companySlug,
    name: displayName,
    availabilityState,
    reportingPeriods: usableYears,
    primaryIndustry,
    summary: summaryText ||
      `Company-memory intelligence is ${availabilityState === "READY" ? "ready" : "partially available"} for ${companySlug}.`,
    importantUnknown,
    questionIds,
  };
}

export async function buildCompanyResearchViewFromDiscovery(
  companySlug: string,
  discovery?: CompanyDiscoverySummary | null,
): Promise<CompanyResearchView | null> {
  const memoryIndex = await loadCompanyMemoryIndex(companySlug);
  if (!memoryIndex) {
    return null;
  }

  const yearlyIndex = await loadYearlyIntelligenceIndex(companySlug);
  const companyIntelligence = await loadCompanyIntelligence(companySlug, yearlyIndex);
  const summaryText = String(companyIntelligence?.business?.industry_profile?.business_summary ?? "").trim();
  const displayName = discovery?.name ?? extractDisplayNameFromSummary(summaryText, companySlug);
  const primaryIndustry = discovery?.primaryIndustry ?? extractPrimaryIndustry(summaryText, companySlug);
  const reportingPeriods = discovery?.reportingPeriods ?? yearsToRange(memoryIndex.usable_years ?? []);
  return {
    schemaVersion: "ask_intrinsiciq.company_research_view.v1",
    company: {
      companySlug,
      companyName: displayName,
      displayName,
      reportingPeriodsCovered: reportingPeriods,
      primaryIndustry,
      shortDescription: summaryText ||
        `Company-memory intelligence is available, but canonical Ask IntrinsicIQ output is still partial for ${companySlug}.`,
    },
    coverage: {
      availableCategoryIds: getFallbackCategories().map((category) => category.id),
      sourcedAnswerCount: 0,
      partiallySupportedAnswerCount: 0,
      unsupportedAnswerCount: 0,
      unavailableAnswerCount: FallbackQuestions.length,
      evidenceStatus: "partial",
      summary:
        summaryText ||
        `Canonical Ask IntrinsicIQ output is not yet available for ${companySlug}; the UI is using a clean partial research shell.`,
    },
    categories: getFallbackCategories(),
    businessJourney: null,
    productsAndServices: [],
    financialVisuals: [],
    generatedAt: new Date().toISOString(),
    sourceState: {
      producer: "prometheus",
      mode: "backend",
      contentStatus: "partial",
      sourceMode: "company_memory",
      summary:
        summaryText ||
        `Canonical Ask IntrinsicIQ output is not yet available for ${companySlug}.`,
      foundSourceCount: reportingPeriods.length,
      missingSourceCount: memoryIndex.incomplete_years?.length ?? 0,
      sourceUpdatedAt: new Date().toISOString(),
      notes: [
        `Available years: ${reportingPeriods.length > 0 ? reportingPeriods.join(", ") : "none"}.`,
      ],
      uncertaintySummary: buildUncertaintySummary(companySlug, memoryIndex, yearlyIndex, false),
    },
  };
}

export async function buildUnavailableResearchAnswerCard(
  companySlug: string,
  questionId: string,
  company: CompanyResearchView,
): Promise<ResearchAnswerCard | null> {
  const question = company.categories
    .flatMap((category) => category.questions)
    .find((entry) => entry.id === questionId);

  if (!question) {
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
    })) as ResearchAnswerCard["nextQuestions"];

  return {
    id: question.answerCardId,
    questionId: question.id,
    title: question.title,
    simpleAnswer: "Research for this question is not complete yet.",
    whyItMatters:
      "The company-memory record exists, but this question does not yet have a canonical Ask answer.",
    keyPoints: [
      `Company: ${company.company.displayName}`,
      `Available years: ${company.company.reportingPeriodsCovered.join(", ") || "none"}`,
    ],
    detailedExplanation:
      "This page is intentionally restrained. It shows that the route works, the company is recognized, and the answer is still incomplete rather than silently borrowed from another company.",
    productsAndServices: [],
    businessJourney: null,
    financialVisualRefs: [],
    evidenceSummary: [
      {
        label: "Availability",
        detail: company.sourceState.summary ?? "Canonical Ask output is not yet available.",
        evidenceStatus: "missing",
      },
    ],
    uncertaintyNote: {
      label: "Research incomplete",
      detail: company.sourceState.uncertaintySummary?.mainUncertainty ?? "This question is not fully researched yet.",
      evidenceStatus: "missing",
    },
    nextQuestions,
    answerStatus: "unavailable",
    questionType: getQuestionPresentationType(questionId),
    generatedAt: company.generatedAt,
  };
}
