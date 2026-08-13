import {
  getCompanyResearch as getDemoCompanyResearch,
  getQuestionAnswer as getDemoQuestionAnswer,
} from "@/src/data/demo-research";
import { buildAskContextV2, buildAskV2Summary } from "@/src/lib/prometheus/ask-v2/context-builder";
import { buildAskPlan } from "@/src/lib/prometheus/ask-v2/router";
import { validateAskAnswerV2, validateAskPlan } from "@/src/lib/prometheus/ask-v2/validators";
import { sanitizeUiList, sanitizeUiText } from "@/src/lib/prometheus/sanitizers";
import { finalizeResearchAnswerForDisplay } from "@/src/lib/ask-intrinsiciq/presentation";
import type {
  CompanyResearchView,
  EvidenceSummary,
  NextQuestion,
  ResearchAnswer,
  ResearchAnswerStatus,
  SupportingPoint,
} from "@/src/types/research";

export type RawSources = {
  pcim: Record<string, unknown> | null;
  truthPack: Record<string, unknown> | null;
  ownerEarningsBridge: Record<string, unknown> | null;
  workingCapitalQuality: Record<string, unknown> | null;
  capitalAllocationRoi: Record<string, unknown> | null;
  perShareCompounding: Record<string, unknown> | null;
  managementCommitments?: Record<string, unknown> | null;
  projectAssessments?: Record<string, unknown> | null;
  projectTimelines?: Record<string, unknown> | null;
  capacityAssessments?: Record<string, unknown> | null;
  capacityTimelines?: Record<string, unknown> | null;
  riskAssessments?: Record<string, unknown> | null;
  riskTimelines?: Record<string, unknown> | null;
  riskEvolution?: Record<string, unknown> | null;
  commentaryAssessments?: Record<string, unknown> | null;
  commentaryTimelines?: Record<string, unknown> | null;
  commentaryThemes?: Record<string, unknown> | null;
  managementQualitySummary?: Record<string, unknown> | null;
  managementQualityDimensions?: Record<string, unknown> | null;
  capitalAllocationOutcomes?: Record<string, unknown> | null;
  capitalAllocationTimelines?: Record<string, unknown> | null;
  promiseTracker?: Record<string, unknown> | null;
  buffettAnalysis: Record<string, unknown> | null;
  grahamAnalysis: Record<string, unknown> | null;
  fisherAnalysis: Record<string, unknown> | null;
  mungerAnalysis: Record<string, unknown> | null;
  lynchAnalysis: Record<string, unknown> | null;
  committeeSynthesis: Record<string, unknown> | null;
  committeeBriefQa: Record<string, unknown> | null;
  panelRunSummary: Record<string, unknown> | null;
  rawDiscoveryBundles?: Array<Record<string, unknown>> | null;
};

type AnswerDraft = {
  answerStatus: ResearchAnswerStatus;
  directAnswer: string;
  explanation: string;
  supportingPoints: SupportingPoint[];
  supportingEvidence: EvidenceSummary[];
  uncertaintyNote: {
    label: string;
    detail: string;
  };
};

const NOT_SUPPORTED = "Not supported by available evidence.";

export function buildCompanyResearchView(
  companySlug: string,
  developmentNote: string | null,
): CompanyResearchView | null {
  const demo = getDemoCompanyResearch(companySlug);

  if (!demo) {
    return null;
  }

  return {
    ...demo,
    developmentNote,
  };
}

export function buildResearchAnswer(
  companySlug: string,
  questionId: string,
  sources: RawSources,
  developmentNote: string | null,
): ResearchAnswer | null {
  const fallback = getDemoQuestionAnswer(companySlug, questionId);

  if (!fallback) {
    return null;
  }

  const askPlan = buildAskPlan(fallback.question || questionId, questionId);
  const planIssues = validateAskPlan(askPlan);
  const sourced = buildKnownAnswer(questionId, fallback, sources);
  const enriched = finalizeAnswer({
    ...sourced,
    developmentNote,
  });
  const askContext = buildAskContextV2(sources, askPlan);
  const askSummary = buildAskV2Summary(askContext);
  const finalized = finalizeResearchAnswerForDisplay({
    ...enriched,
    ...askSummary,
  });
  const answerValidationIssues = validateAskAnswerV2(finalized, askContext);

  return {
    ...finalized,
    askDiagnostics: {
      ...askSummary.askDiagnostics,
      validationStatus: planIssues.length === 0 && answerValidationIssues.length === 0 ? "pass" : answerValidationIssues.length > 0 ? "fail" : "warning",
    },
  };
}

function buildKnownAnswer(
  questionId: string,
  fallback: ResearchAnswer,
  sources: RawSources,
): ResearchAnswer {
  switch (questionId) {
    case "what-does-company-do":
      return applyDraft(
        fallback,
        buildBusinessSummaryAnswer(sources, fallback),
      );
    case "who-are-the-customers":
      return applyDraft(fallback, buildCustomersAnswer(sources));
    case "how-does-it-make-money":
      return applyDraft(fallback, buildMakeMoneyAnswer(sources));
    case "what-makes-the-offering-important":
      return applyDraft(fallback, buildOfferingImportanceAnswer(sources));
    case "where-is-evidence-thin":
      return applyDraft(fallback, buildEvidenceThinAnswer(sources));
    case "are-profits-converting-into-cash":
      return applyDraft(fallback, buildCashConversionAnswer(sources));
    case "what-is-owner-earnings":
      return applyDraft(fallback, buildOwnerEarningsAnswer(sources));
    case "is-working-capital-a-concern":
      return applyDraft(fallback, buildWorkingCapitalConcernAnswer(sources));
    case "are-per-share-economics-improving":
      return applyDraft(fallback, buildPerShareAnswer(sources));
    case "which-financial-assumption-matters-most":
      return applyDraft(fallback, buildFinancialAssumptionAnswer(sources));
    case "what-has-management-promised":
      return applyDraft(fallback, buildManagementPromisesAnswer(sources));
    case "did-past-claims-come-true":
      return applyDraft(fallback, buildPastClaimsAnswer(sources));
    case "how-is-capital-allocated":
      return applyDraft(fallback, buildCapitalAllocationAnswer(sources));
    case "what-incentives-matter":
      return applyDraft(fallback, buildIncentivesAnswer(sources));
    case "what-should-i-ask-ir":
      return applyDraft(fallback, buildAskIrAnswer(sources));
    case "what-would-graham-worry-about":
      return applyDraft(fallback, buildLensAnswer(sources.grahamAnalysis, sources, "graham"));
    case "what-would-buffett-focus-on":
      return applyDraft(fallback, buildLensAnswer(sources.buffettAnalysis, sources, "buffett"));
    case "where-would-fisher-be-curious":
      return applyDraft(fallback, buildLensAnswer(sources.fisherAnalysis, sources, "fisher"));
    case "what-would-munger-avoid":
      return applyDraft(fallback, buildLensAnswer(sources.mungerAnalysis, sources, "munger"));
    case "how-would-lynch-explain-it":
      return applyDraft(fallback, buildLensAnswer(sources.lynchAnalysis, sources, "lynch"));
    case "what-can-break-the-thesis":
      return applyDraft(fallback, buildBreakThesisAnswer(sources));
    case "which-disclosure-is-missing":
      return applyDraft(fallback, buildMissingDisclosureAnswer(sources));
    case "what-evidence-would-change-the-view":
      return applyDraft(fallback, buildChangeViewAnswer(sources));
    case "what-needs-management-clarification":
      return applyDraft(fallback, buildNeedsClarificationAnswer(sources));
    case "what-remains-unresolved":
      return applyDraft(fallback, buildUnresolvedAnswer(sources));
    case "what-are-key-risks":
      return applyDraft(fallback, buildRisksAnswer(sources));
    default:
      return finalizeAnswer(fallback);
  }
}

function buildBusinessSummaryAnswer(
  sources: RawSources,
  fallback: ResearchAnswer,
): AnswerDraft {
  const businessModel = getBusinessModel(sources);
  const directAnswer = sanitizeUiText(
    getString(businessModel, "business_summary") ?? fallback.directAnswer,
  );
  const explanation = sanitizeUiText(
    getString(businessModel, "business_model") ??
      getString(businessModel, "competitive_position_summary") ??
      fallback.explanation,
  );
  const supportingPoints = sanitizeUiList([
    getString(businessModel, "business_model"),
    getString(businessModel, "value_creation"),
    ...getStringArray(businessModel, "characteristics").slice(0, 2),
    getString(businessModel, "competitive_position_summary"),
  ])
    .slice(0, 4)
    .map((detail, index) => ({
      title: ["Business model", "Value creation", "Operating profile", "Positioning"][index] ?? "Business detail",
      detail,
    }));

  return buildDraft("sourced", directAnswer, explanation, supportingPoints, [
    "Supported by the latest business intelligence summary.",
    "Business model, value creation, and positioning are visible in the current source set.",
  ], "Revenue mix by program and the exact customer split are still only partially visible.");
}

function buildCustomersAnswer(sources: RawSources): AnswerDraft {
  const businessModel = getBusinessModel(sources);
  const summary = getString(businessModel, "business_summary");
  const position = getString(businessModel, "competitive_position_summary");
  const buffettRedFlag = getStringArray(sources.buffettAnalysis, "red_flags")[0];

  if (!summary && !position && !buffettRedFlag) {
    return buildNotSupportedAnswer(
      "The current source set does not identify customers with enough specificity to answer this cleanly.",
      "Customer identity matters because concentration, procurement cycles, and switching costs can shape both growth quality and risk.",
      [
        "No clean customer roster or revenue split is visible in the available source set.",
        "Some investor-lens material suggests dependence on government defence and space customers, but not at the detail level needed for a precise customer map.",
      ],
      "Customer concentration is discussed indirectly, but explicit customer mix evidence is limited.",
    );
  }

  return buildDraft(
    "partially_sourced",
    sanitizeUiText(
      "The available evidence points to government defence and space customers, but it does not provide a clean customer-by-customer breakdown.",
    ),
    sanitizeUiText(
      "That still helps: it suggests a procurement-driven customer base where program timing, qualification requirements, and concentration risk matter more than broad retail-style demand.",
    ),
    buildSupportingPoints([
      ["Likely customer set", summary],
      ["Concentration signal", buffettRedFlag],
      ["Why this matters", position],
    ]),
    [
      "Supported indirectly by the business summary and investor-panel risk commentary.",
      "Customer concentration is visible as a risk theme even though exact mix data is not.",
    ],
    "Customer names, revenue concentration, and repeat-order share are not fully disclosed in the available evidence.",
  );
}

function buildMakeMoneyAnswer(sources: RawSources): AnswerDraft {
  const businessModel = getBusinessModel(sources);
  const direct = firstAvailableText(
    getString(businessModel, "business_model"),
    getString(businessModel, "business_summary"),
  );

  if (!direct) {
    return buildNotSupportedAnswer(
      "The available source set does not describe the revenue model clearly enough to answer this with confidence.",
      "How a company makes money affects margin durability, working-capital needs, and how easy the business is to understand.",
      [
        "The current evidence describes expansion activity and operating context more clearly than pricing or contract economics.",
      ],
      "The commercial model is only indirectly visible in the available source set.",
    );
  }

  return buildDraft(
    "partially_sourced",
    sanitizeUiText(
      "The evidence suggests the company makes money by designing, qualifying, and delivering specialized systems and related technical capabilities into long-cycle defence and space programs.",
    ),
    sanitizeUiText(
      "In practice, that looks less like volume-driven commodity manufacturing and more like project, subsystem, and capability delivery where qualification and integration depth matter.",
    ),
    buildSupportingPoints([
      ["Operating model", getString(businessModel, "business_model")],
      ["Value creation", getString(businessModel, "value_creation")],
      ["Competitive context", getString(businessModel, "competitive_position_summary")],
    ]),
    [
      "Supported by the current business-model summary.",
      "The source set is stronger on operating model than on explicit pricing mechanics.",
    ],
    "The available material does not spell out pricing, contract structure, or revenue-recognition mechanics in detail.",
  );
}

function buildOfferingImportanceAnswer(sources: RawSources): AnswerDraft {
  const businessModel = getBusinessModel(sources);
  const buffettFinding = getStringArray(sources.buffettAnalysis, "key_findings")[1];

  return buildDraft(
    hasUsefulText(
      getString(businessModel, "value_creation"),
      buffettFinding,
    )
      ? "partially_sourced"
      : "not_supported",
    sanitizeUiText(
      firstAvailableText(
        "The offering appears important because it sits inside specialized defence and space workflows where qualification, reliability, and integration matter.",
        getString(businessModel, "value_creation"),
      ) ?? NOT_SUPPORTED,
    ),
    sanitizeUiText(
      "That importance is better understood through fit and mission sensitivity than through broad consumer visibility.",
    ),
    buildSupportingPoints([
      ["Value creation", getString(businessModel, "value_creation")],
      ["Qualification edge", buffettFinding],
      ["Operating profile", getString(businessModel, "competitive_position_summary")],
    ]),
    [
      "Supported by business-model and investor-lens positioning.",
      "The source set points to qualification depth and integration rather than mass-market scale.",
    ],
    "The evidence supports strategic relevance more clearly than it supports quantified customer-dependence or pricing power.",
  );
}

function buildEvidenceThinAnswer(sources: RawSources): AnswerDraft {
  const items = sanitizeUiList([
    getStringArray(sources.buffettAnalysis, "open_uncertainties")[0],
    getStringArray(sources.buffettAnalysis, "open_uncertainties")[1],
    getStringArray(sources.truthPack, "precision_limits")[0],
    getStringArray(getRecord(sources.committeeSynthesis, "financial_committee_view"), "missing_financial_data")[0],
  ]);

  return buildDraft(
    items.length > 0 ? "sourced" : "not_supported",
    items.length > 0
      ? "The thinnest evidence is around owner-economics precision, customer concentration detail, and the drivers of working-capital intensity."
      : NOT_SUPPORTED,
    "This matters because those are exactly the gaps that can change how durable the business and its cash generation really are.",
    items.slice(0, 4).map((detail, index) => ({
      title: ["Owner economics", "Customer visibility", "Working capital", "Comparability"][index] ?? "Evidence gap",
      detail,
    })),
    [
      "Supported by investor-panel uncertainties and financial limitations.",
      "The current source set is stronger on broad business framing than on decision-grade precision.",
    ],
    "These gaps are visible in the source set itself, not inferred from UI behavior.",
  );
}

function buildCashConversionAnswer(sources: RawSources): AnswerDraft {
  const fy24Bridge = getFy24Bridge(sources);
  const fy24WorkingCapital = getFy24WorkingCapital(sources);
  const fy24PerShare = getFy24PerShare(sources);

  return buildDraft(
    "sourced",
    sanitizeUiText(
      `FY2024 reported profit is ${formatCrore(
        getNumber(fy24Bridge, "reported_pat"),
      )} and operating cash flow is ${formatCrore(
        getNumber(fy24Bridge, "cfo"),
      )}. A conservative owner-earnings estimate of ${formatCrore(
        getNumber(fy24Bridge, "owner_earnings_estimate"),
      )} is available, but cash conversion still looks stretched because receivable days are ${formatNumber(
        getNumber(fy24WorkingCapital, "receivable_days"),
      )}, inventory days are ${formatNumber(
        getNumber(fy24WorkingCapital, "inventory_days"),
      )}, and the cash conversion cycle is ${formatNumber(
        getNumber(fy24WorkingCapital, "cash_conversion_cycle"),
      )} days.`,
    ),
    "Profit has some cash support, but the working-capital burden is heavy enough that the quality of conversion still deserves caution.",
    buildSupportingPoints([
      [
        "Profit versus cash",
        `FY2024 reported profit is ${formatCrore(getNumber(fy24Bridge, "reported_pat"))}, while operating cash flow is ${formatCrore(getNumber(fy24Bridge, "cfo"))}.`,
      ],
      [
        "Owner earnings",
        `A conservative owner-earnings estimate of ${formatCrore(getNumber(fy24Bridge, "owner_earnings_estimate"))} is available after identified capex.`,
      ],
      [
        "Working capital",
        `Receivable days are ${formatNumber(getNumber(fy24WorkingCapital, "receivable_days"))}, inventory days are ${formatNumber(getNumber(fy24WorkingCapital, "inventory_days"))}, and payable days are ${formatNumber(getNumber(fy24WorkingCapital, "payable_days"))}.`,
      ],
      [
        "Per-share context",
        `Owner earnings per share is ${formatPerShare(getNumber(fy24PerShare, "owner_earnings_per_share"))}.`,
      ],
    ]),
    [
      "Supported by the FY2024 financial truth summary.",
      "Supported by owner-earnings and working-capital summaries.",
      firstAvailableText(
        getStringArray(fy24Bridge, "warnings")[0],
        getStringArray(fy24Bridge, "owner_earnings_warnings")[0],
      ),
    ],
    firstAvailableText(
      getStringArray(fy24Bridge, "warnings")[0],
      "Maintenance versus growth capex split is not fully disclosed, so owner-earnings precision remains limited.",
    ) ?? "Cash conversion precision remains limited.",
  );
}

function buildOwnerEarningsAnswer(sources: RawSources): AnswerDraft {
  const fy24Bridge = getFy24Bridge(sources);
  const owner = getNumber(fy24Bridge, "owner_earnings_estimate");

  if (typeof owner !== "number") {
    return buildNotSupportedAnswer(
      "Owner earnings are not supported cleanly in the available evidence.",
      "Owner earnings matter because they try to translate accounting performance into owner-oriented cash generation after reinvestment needs.",
      [
        "The current source set does not provide a reliable owner-earnings estimate.",
      ],
      "Without a usable bridge, owner-oriented cash generation stays uncertain.",
    );
  }

  return buildDraft(
    "sourced",
    `A conservative FY2024 owner-earnings estimate of ${formatCrore(owner)} is available in the current evidence set.`,
    "That estimate is useful because it gives a more owner-oriented read than reported profit alone, but it still needs to be handled carefully because the capex split is not fully disclosed.",
    buildSupportingPoints([
      ["Current estimate", `FY2024 owner earnings are estimated at ${formatCrore(owner)}.`],
      ["Why conservative", `The bridge uses identified capex and avoids claiming more precision than the evidence supports.`],
      ["Key limitation", firstAvailableText(getStringArray(fy24Bridge, "warnings")[0], getStringArray(sources.truthPack, "precision_limits")[0])],
    ]),
    [
      "Supported by the owner-earnings bridge.",
      "Supported by the financial truth summary's precision limits.",
    ],
    firstAvailableText(
      getStringArray(fy24Bridge, "warnings")[0],
      "Maintenance versus growth capex is still not split clearly, so the estimate should be treated as conservative rather than exact.",
    ) ?? "Owner-earnings precision remains limited.",
  );
}

function buildWorkingCapitalConcernAnswer(sources: RawSources): AnswerDraft {
  const fy24WorkingCapital = getFy24WorkingCapital(sources);

  return buildDraft(
    "sourced",
    sanitizeUiText(
      `Yes. FY2024 working-capital intensity looks severe, with receivable days at ${formatNumber(
        getNumber(fy24WorkingCapital, "receivable_days"),
      )}, inventory days at ${formatNumber(
        getNumber(fy24WorkingCapital, "inventory_days"),
      )}, and a cash conversion cycle of ${formatNumber(
        getNumber(fy24WorkingCapital, "cash_conversion_cycle"),
      )} days.`,
    ),
    "Working capital matters because it can trap cash even when margins and reported profits look strong.",
    buildSupportingPoints([
      ["Receivables", `Receivable days are ${formatNumber(getNumber(fy24WorkingCapital, "receivable_days"))}.`],
      ["Inventory", `Inventory days are ${formatNumber(getNumber(fy24WorkingCapital, "inventory_days"))}.`],
      ["Cycle length", `Cash conversion cycle is ${formatNumber(getNumber(fy24WorkingCapital, "cash_conversion_cycle"))} days.`],
      ["Risk signal", firstAvailableText(getString(fy24WorkingCapital, "cash_strain_risk"), getString(fy24WorkingCapital, "working_capital_intensity_status"))],
    ]),
    [
      "Supported by the working-capital quality drilldown.",
      "The current evidence explicitly flags elevated cash-strain risk.",
    ],
    "The source set does not fully explain whether these numbers come from normal project timing, billing structure, or collection pressure.",
  );
}

function buildPerShareAnswer(sources: RawSources): AnswerDraft {
  const fy24PerShare = getFy24PerShare(sources);
  const perShareWarning = firstAvailableText(
    getStringArray(sources.perShareCompounding, "warnings")[0],
    getStringArray(sources.truthPack, "precision_limits")[0],
  );

  return buildDraft(
    "partially_sourced",
    sanitizeUiText(
      `The current evidence shows FY2024 owner earnings per share at ${formatPerShare(
        getNumber(fy24PerShare, "owner_earnings_per_share"),
      )} and book value per share at ${formatPerShare(
        getNumber(fy24PerShare, "book_value_per_share"),
      )}, but it does not yet support a clean multi-year improvement judgment.`,
    ),
    "Per-share economics matter because they show whether value is compounding for each shareholder rather than only at the aggregate company level.",
    buildSupportingPoints([
      ["Owner earnings per share", `${formatPerShare(getNumber(fy24PerShare, "owner_earnings_per_share"))} in FY2024.`],
      ["Book value per share", `${formatPerShare(getNumber(fy24PerShare, "book_value_per_share"))} in FY2024.`],
      ["EPS context", `${formatPerShare(getNumber(fy24PerShare, "eps_basic"))} basic EPS is visible for FY2024.`],
      ["Comparability limit", perShareWarning],
    ]),
    [
      "Supported by the per-share compounding analysis.",
      "Multi-year comparability is limited by share-count precision gaps.",
    ],
    perShareWarning ?? "A clean multi-year per-share trend is not yet well supported.",
  );
}

function buildFinancialAssumptionAnswer(sources: RawSources): AnswerDraft {
  const question = firstAvailableText(
    getStringArray(getRecord(sources.committeeSynthesis, "financial_committee_view"), "investor_questions_from_financials")[0],
    getStringArray(sources.truthPack, "investor_relevant_questions")[0],
  );

  return buildDraft(
    question ? "sourced" : "not_supported",
    question
      ? "The most important financial assumption is how much of current capex is maintenance versus growth."
      : NOT_SUPPORTED,
    "That assumption drives how much of current cash generation is truly distributable versus how much is needed just to sustain the business.",
    buildSupportingPoints([
      ["Core assumption", question],
      ["Why it matters", getStringArray(sources.truthPack, "precision_limits")[0]],
      ["Decision impact", "A different maintenance-capex assumption can materially change how conservative the owner-earnings view should be."],
    ]),
    [
      "Supported by committee financial questions and precision limits.",
    ],
    "Without a maintenance-versus-growth split, owner-oriented cash interpretation remains approximate.",
  );
}

function buildManagementPromisesAnswer(sources: RawSources): AnswerDraft {
  const commitments = getRecordArray(sources.managementCommitments, "commitments");
  const promiseTracker = getRecordArray(sources.promiseTracker, "promises");
  const topCommitments = commitments.filter((item) => getString(item, "normalized_commitment") || getString(item, "delivery_assessment")).slice(0, 4);

  if (topCommitments.length === 0 && promiseTracker.length === 0) {
    return buildNotSupportedAnswer(
      "The available evidence does not document management promises clearly enough to summarize them responsibly.",
      "Promise tracking matters because it helps separate credible execution from polished narrative.",
      [
        "The current source set is stronger on business and financial artifacts than on a clean promise ledger.",
      ],
      "Management-commitment evidence is thin in the current source set.",
    );
  }

  return buildDraft(
    "sourced",
    sanitizeUiText(
      topCommitments.length > 0
        ? `Management committed to ${topCommitments
            .map((item) => getString(item, "normalized_commitment") || getString(item, "topic") || "a business objective")
            .slice(0, 3)
            .join("; ")}.`
        : "The available company memory preserves promise themes, but not a clean commitment ledger.",
    ),
    "That matters because promises should be checked against later evidence, not accepted as narrative.",
    buildSupportingPoints(
      topCommitments.slice(0, 4).map((item, index) => [
        ["Commitment", "Status", "Delivery read", "Timing"][index] ?? "Commitment",
        [
          getString(item, "topic"),
          getString(item, "normalized_commitment"),
          getString(item, "status"),
          getString(item, "delivery_assessment"),
          getString(item, "expected_timeframe"),
        ]
          .filter(Boolean)
          .join(" • "),
      ]),
    ),
    [
      "Supported by the management-commitments memory layer.",
      promiseTracker.length > 0 ? "Promise-tracker evidence adds additional historical context." : "",
    ],
    "Execution should be judged by later evidence, not by the original promise wording alone.",
  );
}

function buildPastClaimsAnswer(sources: RawSources): AnswerDraft {
  const commitments = getRecordArray(sources.managementCommitments, "commitments");
  const delivered = commitments.filter((item) => /delivered|completed|fulfilled/i.test(`${getString(item, "status")} ${getString(item, "delivery_assessment")}`));
  const delayed = commitments.filter((item) => /delay|unable to verify|partial/i.test(`${getString(item, "status")} ${getString(item, "delivery_assessment")}`));
  const unresolved = commitments.filter((item) => /unable to verify|unknown|partial/i.test(`${getString(item, "status")} ${getString(item, "delivery_assessment")}`));

  if (commitments.length === 0) {
    return buildNotSupportedAnswer(
      "Past claim versus delivery is not supported by available evidence.",
      "This matters because management quality is easier to judge by follow-through than by messaging alone.",
      [
        "The current source set does not provide a reliable time-linked promise-and-outcome comparison.",
        "Using investor-lens narrative alone would risk overstating what can really be verified.",
      ],
      "A cleaner management timeline would be needed before this can be answered responsibly.",
    );
  }

  const deliveredTopics = delivered
    .map((item) => getString(item, "topic") || getString(item, "normalized_commitment") || "a commitment")
    .slice(0, 2);
  const delayedTopics = delayed
    .map((item) => getString(item, "topic") || getString(item, "normalized_commitment") || "a commitment")
    .slice(0, 2);
  const unresolvedTopics = unresolved
    .map((item) => getString(item, "topic") || getString(item, "normalized_commitment") || "a commitment")
    .slice(0, 2);

  return buildDraft(
    "sourced",
    sanitizeUiText(
      delivered.length > 0
        ? `Some promises appear to have been delivered, including ${deliveredTopics.join(" and ")}. A few commitments remain delayed or unresolved, so the record is better than a blank check but not a full clean sweep.`
        : "The commitments show progress, but not enough explicit delivery evidence to call the record fully complete.",
    ),
    "The right comparison is promise versus later evidence, not promise versus aspiration. The current record looks mixed: some commitments progressed, while others remain delayed or only partially verified.",
    buildSupportingPoints([
      ["Delivered", deliveredTopics.join(", ") || "No clearly delivered commitment found"],
      ["Delayed", delayedTopics.join(", ") || "No clearly delayed commitment found"],
      ["Unresolved", unresolvedTopics.join(", ") || "No clearly unresolved commitment found"],
      ["Latest lesson", "Execution appears stronger where the evidence moves from announcement into operating reality."],
    ]),
    [
      "Supported by the management-commitments memory layer.",
      "Later project and capacity evidence helps check whether the promise turned into execution.",
    ],
    "A commitment should not be treated as delivered unless later evidence actually supports that reading.",
  );
}

function buildCapitalAllocationAnswer(sources: RawSources): AnswerDraft {
  const entries = getRecordArray(sources.capitalAllocationRoi, "entries");
  const outcomes = getRecordArray(sources.capitalAllocationOutcomes, "outcomes");
  const timeline = getRecordArray(sources.capitalAllocationTimelines, "timeline");
  const firstEntry = entries[0] || outcomes[0] || timeline[0];

  if (entries.length === 0 && outcomes.length === 0 && timeline.length === 0) {
    return buildNotSupportedAnswer(
      "Capital allocation is not supported cleanly in the available evidence.",
      "Capital allocation matters because it shows whether management is converting financial flexibility into durable capacity, returns, or avoidable dilution.",
      [
        "The current source set does not provide a reliable capital-allocation ledger.",
      ],
      "The capital-allocation outcome layer is unavailable or empty in the current environment.",
    );
  }

  return buildDraft(
    "sourced",
    sanitizeUiText(
      outcomes.length > 0
        ? `Capital appears to have been deployed into ${outcomes
            .map((item) => getString(item, "title") || getString(item, "objective") || getString(item, "capital_use") || "a business area")
            .slice(0, 3)
            .join("; ")}.`
        : "Capital appears to be allocated toward facility, technology, and operating-capacity buildout, with some shareholder distributions as well.",
    ),
    "Capital allocation matters because it shows whether management is converting financial flexibility into durable capacity, returns, or avoidable dilution.",
    buildSupportingPoints([
      ["Current use", firstAvailableText(getString(firstEntry, "capital_use"), getString(firstEntry, "entry_summary"), getString(firstEntry, "outcome"), getString(firstEntry, "execution_summary"))],
      ["Shareholder distribution", firstAvailableText(getString(firstEntry, "shareholder_distribution"), getStringArray(sources.fisherAnalysis, "key_findings")[2])],
      ["ROI limit", firstAvailableText(getStringArray(sources.buffettAnalysis, "red_flags")[1], getString(firstEntry, "progression_summary"))],
      ["Committee view", getStringArray(getRecord(sources.committeeSynthesis, "financial_committee_view"), "investor_questions_from_financials")[0]],
    ]),
    [
      "Supported by the capital-allocation ledger and investor-panel commentary.",
      outcomes.length > 0 ? "Capital-allocation outcomes add a later-evidence layer." : "The use of capital is clearer than the eventual return on that capital.",
    ],
    firstAvailableText(
      getString(firstEntry, "investor_implication"),
      "ROI outcomes are still only partially measurable from the available evidence.",
    ) ?? "ROI outcomes are still only partially measurable from the available evidence.",
  );
}

function buildIncentivesAnswer(sources: RawSources): AnswerDraft {
  const munger = sources.mungerAnalysis;
  const directSignals = sanitizeUiList([
    getStringArray(munger, "key_findings")[0],
    getStringArray(munger, "key_findings")[1],
    getStringArray(munger, "red_flags")[1],
    getStringArray(munger, "red_flags")[2],
  ]);

  return buildDraft(
    directSignals.length > 0 ? "partially_sourced" : "not_supported",
    directSignals.length > 0
      ? "The main incentive questions here are around capital-raising discipline, related-party exposure, and how transparent management is about the use of shareholder capital."
      : NOT_SUPPORTED,
    "Incentives matter because even a good business can compound poorly if the people allocating capital are not aligned with outside shareholders.",
    directSignals.slice(0, 4).map((detail, index) => ({
      title: ["Equity issuance", "Related-party exposure", "Capital transparency", "Monitoring need"][index] ?? "Incentive signal",
      detail,
    })),
    [
      "Supported mainly by the Munger lens and committee risk synthesis.",
      "This is stronger as a monitoring answer than as a final governance verdict.",
    ],
    "The current source set highlights incentive questions more clearly than it answers them.",
  );
}

function buildAskIrAnswer(sources: RawSources): AnswerDraft {
  const questions = sanitizeUiList([
    ...getQuestionTexts(getRecord(sources.committeeSynthesis, "investigation_questions")),
    ...getStringArray(getRecord(sources.committeeSynthesis, "financial_committee_view"), "investor_questions_from_financials"),
  ]).slice(0, 4);

  return buildDraft(
    questions.length > 0 ? "sourced" : "not_supported",
    questions.length > 0
      ? "The best IR questions are the ones that clarify capex split, working-capital drivers, share-count comparability, and the basis of reported financials."
      : NOT_SUPPORTED,
    "These questions matter because they target the exact evidence gaps that limit confidence today.",
    questions.map((detail, index) => ({
      title: ["Capex split", "Working capital", "Share-count comparability", "Reporting basis"][index] ?? "IR question",
      detail,
    })),
    [
      "Supported by committee investigation questions and financial follow-ups.",
    ],
    "The available evidence is strong enough to suggest the questions, but not always to answer them.",
  );
}

function buildLensAnswer(
  analysis: Record<string, unknown> | null,
  sources: RawSources,
  lens: "graham" | "buffett" | "fisher" | "munger" | "lynch",
): AnswerDraft {
  const assessment = getRecord(analysis, "assessment");
  const keyFindings = getStringArray(analysis, "key_findings");
  const redFlags = getStringArray(analysis, "red_flags");
  const uncertainties = getStringArray(analysis, "open_uncertainties");
  const committeeSummary = getString(getRecord(sources.committeeSynthesis, "overall_committee_view"), "summary");

  const direct = firstAvailableText(
    ...Object.values(assessment).filter((value): value is string => typeof value === "string"),
    committeeSummary,
  );

  return buildDraft(
    direct ? "sourced" : "not_supported",
    direct ?? NOT_SUPPORTED,
    lensWhyItMatters(lens),
    buildSupportingPoints([
      ["First signal", keyFindings[0]],
      ["Second signal", keyFindings[1]],
      ["Main caution", redFlags[0]],
      ["Main uncertainty", uncertainties[0]],
    ]),
    [
      `Supported by the ${lens} investor view.`,
      "Cross-checked against the committee synthesis where useful.",
    ],
    uncertainties[0] ?? "This lens remains limited by the available evidence set.",
  );
}

function buildBreakThesisAnswer(sources: RawSources): AnswerDraft {
  const risks = getRiskTexts(sources).slice(0, 4);

  return buildDraft(
    risks.length > 0 ? "sourced" : "not_supported",
    risks.length > 0
      ? "The thesis would be pressured most by severe working-capital strain, customer concentration, weak cash conversion, or capital deployment that does not earn back attractive returns."
      : NOT_SUPPORTED,
    "Break points matter because they force the diligence process to focus on what would truly damage the business case rather than on ordinary volatility.",
    risks.map((detail, index) => ({
      title: ["Working capital", "Concentration", "Capital allocation", "Evidence quality"][index] ?? "Risk",
      detail,
    })),
    [
      "Supported by committee and investor-panel risk outputs.",
    ],
    "Some risks are directional because the source set is stronger on flags than on quantified scenario analysis.",
  );
}

function buildMissingDisclosureAnswer(sources: RawSources): AnswerDraft {
  const missing = sanitizeUiList([
    ...getStringArray(getRecord(sources.committeeSynthesis, "financial_committee_view"), "missing_financial_data"),
    ...getStringArray(sources.truthPack, "precision_limits"),
  ]).slice(0, 4);

  return buildDraft(
    missing.length > 0 ? "sourced" : "not_supported",
    missing.length > 0
      ? "The most important missing disclosures are the maintenance-versus-growth capex split, clean share-count comparability, and a clearer basis for financial comparison."
      : NOT_SUPPORTED,
    "Disclosure gaps matter because they limit how confidently profits, owner earnings, and per-share progress can be interpreted.",
    missing.map((detail, index) => ({
      title: ["Capex split", "Reporting basis", "Share-count comparability", "Other precision limit"][index] ?? "Disclosure gap",
      detail,
    })),
    [
      "Supported by committee and truth-pack limitation fields.",
    ],
    "These are the cleanest documented disclosure gaps in the current evidence set.",
  );
}

function buildChangeViewAnswer(sources: RawSources): AnswerDraft {
  const questions = getQuestionTexts(getRecord(sources.committeeSynthesis, "investigation_questions"));

  return buildDraft(
    questions.length > 0 ? "partially_sourced" : "not_supported",
    questions.length > 0
      ? "The view would change most if the company provided cleaner evidence on capex split, working-capital drivers, share-count comparability, and reporting basis."
      : NOT_SUPPORTED,
    "This matters because better evidence should change conviction only when it resolves a genuinely important unknown.",
    questions.slice(0, 4).map((detail, index) => ({
      title: ["Capex", "Shares", "Basis", "Working capital"][index] ?? "Evidence request",
      detail,
    })),
    [
      "Supported by committee investigation questions.",
    ],
    "The available evidence identifies the pressure points clearly, but not every possible confirming signal.",
  );
}

function buildNeedsClarificationAnswer(sources: RawSources): AnswerDraft {
  const questions = sanitizeUiList([
    ...getQuestionTexts(getRecord(sources.committeeSynthesis, "investigation_questions")),
    ...getStringArray(getRecord(sources.committeeSynthesis, "financial_committee_view"), "investor_questions_from_financials"),
  ]);

  return buildDraft(
    questions.length > 0 ? "sourced" : "not_supported",
    questions.length > 0
      ? "Management most needs to clarify capex classification, working-capital drivers, share-count comparability, and how to interpret the reported basis consistently."
      : NOT_SUPPORTED,
    "Clarification matters because these are the points where missing context can change whether current numbers look strong or only superficially strong.",
    questions.slice(0, 4).map((detail, index) => ({
      title: ["Capex clarification", "Working capital", "Share counts", "Basis consistency"][index] ?? "Clarification need",
      detail,
    })),
    [
      "Supported by committee follow-up questions and financial limitations.",
    ],
    "This answer identifies follow-up areas, not management intent.",
  );
}

function buildUnresolvedAnswer(sources: RawSources): AnswerDraft {
  const unresolved = sanitizeUiList([
    ...getUnknownTexts(getRecordArray(sources.committeeSynthesis, "critical_unknowns")),
    ...getStringArray(sources.buffettAnalysis, "open_uncertainties"),
  ]).slice(0, 4);

  return buildDraft(
    unresolved.length > 0 ? "sourced" : "not_supported",
    unresolved.length > 0
      ? "What remains unresolved is mostly about owner-economics precision, customer concentration, share-count comparability, and why working capital is so demanding."
      : NOT_SUPPORTED,
    "Keeping unresolved issues visible matters because early conviction is most dangerous when the open questions are hidden.",
    unresolved.map((detail, index) => ({
      title: ["Owner economics", "Share counts", "Reporting basis", "Working capital"][index] ?? "Unresolved issue",
      detail,
    })),
    [
      "Supported by committee unknowns and investor-panel uncertainties.",
    ],
    "These unresolved points come directly from the current evidence set.",
  );
}

function buildRisksAnswer(sources: RawSources): AnswerDraft {
  const committee = sources.committeeSynthesis;
  const truthPack = sources.truthPack;
  const riskAssessments = getRecordArray(sources.riskAssessments, "assessments");
  const riskEvolution = getRecordArray(sources.riskEvolution, "risks");
  const topRisks = [...riskAssessments, ...riskEvolution].slice(0, 3);

  return buildDraft(
    "sourced",
    sanitizeUiText(
      topRisks.length > 0
        ? `The biggest risks remain ${topRisks
            .map((item) => getString(item, "risk_name") || getString(item, "normalized_risk") || getString(item, "risk") || "a business risk")
            .slice(0, 3)
            .join("; ")}.`
        : getString(getRecord(committee, "overall_committee_view"), "summary") ?? NOT_SUPPORTED,
    ),
    "The most important risks are not short-term market swings. They are working-capital strain, concentration, and the limits of what the current evidence can prove about owner economics.",
    buildSupportingPoints([
      [
        "Working-capital strain",
        firstAvailableText(
          getStringArray(getRecord(committee, "financial_committee_view"), "financial_concerns")[0],
          getString(topRisks[0], "risk_mechanism"),
        ),
      ],
      [
        "Concentration",
        firstAvailableText(
          getStringArray(getRecord(committee, "financial_committee_view"), "financial_concerns")[1],
          getString(topRisks[1], "risk_mechanism"),
        ),
      ],
      [
        "Precision limits",
        getStringArray(getRecord(committee, "financial_committee_view"), "missing_financial_data")[0],
      ],
      [
        "Next diligence step",
        getStringArray(getRecord(committee, "financial_committee_view"), "investor_questions_from_financials")[0],
      ],
    ]),
    [
      "Supported by the committee synthesis and investor-panel summaries.",
      firstAvailableText(
        getStringArray(truthPack, "precision_limits")[0],
        getStringArray(getRecord(committee, "financial_committee_view"), "missing_financial_data")[1],
      ),
    ],
    firstAvailableText(
      getStringArray(truthPack, "precision_limits")[0],
      "Some of the risk picture still depends on missing precision around capex split, share-count comparability, and customer concentration.",
    ) ?? "Risk precision remains limited.",
  );
}

function applyDraft(fallback: ResearchAnswer, draft: AnswerDraft): ResearchAnswer {
  return finalizeAnswer({
    ...fallback,
    state: draft.answerStatus === "placeholder" ? "placeholder" : "prepared",
    answerStatus: draft.answerStatus,
    directAnswer: draft.directAnswer,
    conciseAnswer: draft.directAnswer,
    explanation: draft.explanation,
    whyItMatters: draft.explanation,
    supportingPoints: draft.supportingPoints.slice(0, 4),
    supportingEvidence: draft.supportingEvidence.slice(0, 3),
    evidenceSummary: draft.supportingEvidence.slice(0, 3),
    uncertaintyNote: draft.uncertaintyNote,
  });
}

function finalizeAnswer(answer: ResearchAnswer): ResearchAnswer {
  const nextQuestions = buildNextQuestions(answer);

  return {
    ...answer,
    questionTitle: answer.questionTitle ?? answer.question,
    conciseAnswer: answer.conciseAnswer ?? answer.directAnswer,
    whyItMatters: answer.whyItMatters ?? answer.explanation,
    evidenceSummary: answer.evidenceSummary ?? answer.supportingEvidence,
    answerStatus: answer.answerStatus ?? (answer.state === "placeholder" ? "placeholder" : "sourced"),
    nextQuestionIds: answer.nextQuestionIds.slice(0, 3),
    nextQuestions,
  };
}

function buildNextQuestions(answer: ResearchAnswer): NextQuestion[] {
  return answer.nextQuestionIds.slice(0, 3).map((questionId) => ({
    questionId,
    title: QUESTION_TITLES[questionId] ?? answer.question,
  }));
}

function buildDraft(
  answerStatus: ResearchAnswerStatus,
  directAnswer: string,
  explanation: string,
  supportingPoints: SupportingPoint[],
  evidence: Array<string | null | undefined>,
  uncertaintyDetail: string,
): AnswerDraft {
  return {
    answerStatus,
    directAnswer: sanitizeUiText(directAnswer),
    explanation: sanitizeUiText(explanation),
    supportingPoints: supportingPoints
      .map((point) => ({
        title: sanitizeUiText(point.title),
        detail: sanitizeUiText(point.detail),
      }))
      .filter((point) => point.detail.length > 0)
      .slice(0, 4),
    supportingEvidence: buildEvidence(evidence),
    uncertaintyNote: {
      label: "Uncertainty note",
      detail: sanitizeUiText(uncertaintyDetail),
    },
  };
}

function buildNotSupportedAnswer(
  directAnswer: string,
  explanation: string,
  supportingDetails: string[],
  uncertaintyDetail: string,
): AnswerDraft {
  return buildDraft(
    "not_supported",
    directAnswer,
    explanation,
    supportingDetails.slice(0, 4).map((detail, index) => ({
      title: ["Current limitation", "Why it matters", "Evidence boundary", "What is still needed"][index] ?? "Limitation",
      detail,
    })),
    [
      "The current source set does not support a stronger answer.",
      "The response is intentionally conservative rather than inferred beyond the evidence.",
    ],
    uncertaintyDetail,
  );
}

function buildEvidence(items: Array<string | null | undefined>): EvidenceSummary[] {
  return sanitizeUiList(items).slice(0, 3).map((detail, index) => ({
    label: ["Support", "Context", "Limitation"][index] ?? "Support",
    detail,
  }));
}

function buildSupportingPoints(
  items: Array<[string, string | null | undefined]>,
): SupportingPoint[] {
  return items
    .map(([title, detail]) => ({
      title,
      detail: sanitizeUiText(detail),
    }))
    .filter((item) => item.detail.length > 0);
}

function getBusinessModel(sources: RawSources) {
  return getRecord(
    getRecord(
      getRecord(sources.pcim, "business_understanding"),
      "latest_business_view",
    ),
    "business_model",
  );
}

function getFy24Bridge(sources: RawSources) {
  return findByYear(getRecordArray(sources.ownerEarningsBridge, "bridges"), "fy24");
}

function getFy24WorkingCapital(sources: RawSources) {
  return findByYear(getRecordArray(sources.workingCapitalQuality, "drilldown"), "fy24");
}

function getFy24PerShare(sources: RawSources) {
  return findByYear(getRecordArray(sources.perShareCompounding, "analysis"), "fy24");
}

function getRiskTexts(sources: RawSources) {
  const committeeRisks = getRecordArray(sources.committeeSynthesis, "most_important_risks").flatMap(
    (item) => sanitizeUiList([getString(item, "risk"), getString(item, "why_it_matters")]),
  );
  return sanitizeUiList([
    ...committeeRisks,
    ...getStringArray(sources.buffettAnalysis, "red_flags"),
    ...getStringArray(sources.grahamAnalysis, "red_flags"),
    ...getStringArray(sources.mungerAnalysis, "red_flags"),
  ]);
}

function getUnknownTexts(items: Array<Record<string, unknown>>) {
  return items.flatMap((item) =>
    sanitizeUiList([getString(item, "unknown"), getString(item, "why_it_matters")]),
  );
}

function getQuestionTexts(items: Record<string, unknown>) {
  return getRecordArray({ items }, "items").flatMap((item) =>
    sanitizeUiList([getString(item, "question")]),
  );
}

function lensWhyItMatters(lens: string) {
  switch (lens) {
    case "graham":
      return "This lens matters because it stresses downside protection, cash realism, and whether weak conversion can undermine a seemingly healthy business.";
    case "buffett":
      return "This lens matters because it tests whether business quality and capital allocation remain understandable and durable.";
    case "fisher":
      return "This lens matters because strong growth only deserves confidence when execution, reinvestment, and funding quality are real.";
    case "munger":
      return "This lens matters because governance and incentives can damage even a good business when capital discipline weakens.";
    case "lynch":
      return "This lens matters because the business story should stay understandable when checked against the numbers.";
    default:
      return "This lens matters because it frames what evidence deserves the closest attention.";
  }
}

function firstAvailableText(...values: Array<string | null | undefined>) {
  return values.find((value) => typeof value === "string" && value.trim().length > 0);
}

function hasUsefulText(...values: Array<string | null | undefined>) {
  return Boolean(firstAvailableText(...values));
}

function findByYear(
  items: Array<Record<string, unknown>>,
  year: string,
) {
  const candidates = [year.toLowerCase(), year.toUpperCase()];

  return (
    items.find((item) => {
      const rawValues = [
        item?.fiscal_year,
        item?.year,
        item?.fy,
        item?.fiscalYear,
      ]
        .filter((value): value is string | number => value !== null && value !== undefined)
        .map((value) => String(value).toLowerCase());

      return candidates.some((candidate) => rawValues.includes(candidate));
    }) ?? items[items.length - 1] ?? {}
  );
}

function formatCrore(value: number | null | undefined) {
  return typeof value === "number" ? `₹${value.toFixed(2)} crore` : "not yet visible";
}

function formatNumber(value: number | null | undefined) {
  return typeof value === "number" ? value.toFixed(1) : "not yet visible";
}

function formatPerShare(value: number | null | undefined) {
  return typeof value === "number" ? `₹${value.toFixed(2)} per share` : "not yet visible";
}

function getRecord(
  value: Record<string, unknown> | null | undefined,
  key: string,
): Record<string, unknown> {
  const nested = value?.[key];
  return nested && typeof nested === "object" && !Array.isArray(nested)
    ? (nested as Record<string, unknown>)
    : {};
}

function getRecordArray(
  value: Record<string, unknown> | null | undefined,
  key: string,
): Array<Record<string, unknown>> {
  const nested = value?.[key];

  if (!Array.isArray(nested)) {
    return [];
  }

  return nested.filter(
    (item): item is Record<string, unknown> =>
      typeof item === "object" && item !== null && !Array.isArray(item),
  );
}

function getString(
  value: Record<string, unknown> | null | undefined,
  key: string,
) {
  const nested = value?.[key];
  return typeof nested === "string" ? nested : undefined;
}

function getStringArray(
  value: Record<string, unknown> | null | undefined,
  key: string,
) {
  const nested = value?.[key];
  return Array.isArray(nested)
    ? nested.filter((item): item is string => typeof item === "string")
    : [];
}

function getNumber(
  value: Record<string, unknown> | null | undefined,
  key: string,
) {
  const nested = value?.[key];
  return typeof nested === "number" ? nested : undefined;
}

const QUESTION_TITLES: Record<string, string> = {
  "what-does-company-do": "What does the company do?",
  "who-are-the-customers": "Who are the customers?",
  "how-does-it-make-money": "How does it make money?",
  "what-makes-the-offering-important": "What makes the offering important?",
  "where-is-evidence-thin": "Where is evidence thin?",
  "are-profits-converting-into-cash": "Is profit converting into cash?",
  "what-is-owner-earnings": "What is owner earnings?",
  "is-working-capital-a-concern": "Is working capital a concern?",
  "are-per-share-economics-improving": "Are per-share economics improving?",
  "which-financial-assumption-matters-most": "Which financial assumption matters most?",
  "what-has-management-promised": "What has management promised?",
  "did-past-claims-come-true": "Did past claims come true?",
  "how-is-capital-allocated": "How is capital allocated?",
  "what-incentives-matter": "What incentives matter?",
  "what-should-i-ask-ir": "What should I ask IR?",
  "what-would-graham-worry-about": "What would Graham worry about?",
  "what-would-buffett-focus-on": "What would Buffett focus on?",
  "where-would-fisher-be-curious": "Where would Fisher be curious?",
  "what-would-munger-avoid": "What would Munger avoid?",
  "how-would-lynch-explain-it": "How would Lynch explain it?",
  "what-can-break-the-thesis": "What can break the thesis?",
  "which-disclosure-is-missing": "Which disclosure is missing?",
  "what-evidence-would-change-the-view": "What evidence would change the view?",
  "what-needs-management-clarification": "What needs management clarification?",
  "what-remains-unresolved": "What remains unresolved?",
  "what-are-key-risks": "What are key risks?",
};
