import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import type {
  BusinessJourney,
  ProductServiceGroup,
  ResearchAnswerCard,
} from "@/src/types";
import type { InvestorInterpretation } from "@/src/types/investor-interpretation";
import type { ProgressionInsight } from "@/src/types/progression";
import type { QuestionPresentationType } from "@/src/types/question-presentation";
import { readJsonIfExists } from "@/src/lib/prometheus/read-json";
import {
  buildUnavailableResearchAnswerCard,
  resolveInternalKey,
} from "@/src/lib/ask-intrinsiciq/company-discovery";
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
import {
  getCanaryConfig,
  isCanaryEligible,
} from "@/src/lib/ask-intrinsiciq/canary-config";

export type AnswerSource = "HYBRID_CANARY" | "PRODUCTION_FALLBACK";

export type ResearchAnswerCardWithSource = {
  card: ResearchAnswerCard;
  source: AnswerSource;
};

type DependencyProvenanceEntry = {
  logical_source: string;
  artifact_path: string;
  artifact_timestamp: string;
  used_as: "primary" | "secondary" | "enrichment";
};

/**
 * Returns FRESH when all registered dependencies have timestamps ≤ cardGeneratedAt.
 * Returns STALE when any dependency timestamp is newer.
 * Returns UNKNOWN when provenance is absent or timestamps cannot be compared.
 *
 * UNKNOWN is NOT silently treated as FRESH — callers must handle it explicitly.
 */
function checkAnswerCardFreshness(
  provenance: DependencyProvenanceEntry[] | null | undefined,
  cardGeneratedAt: string | null | undefined,
): "FRESH" | "STALE" | "UNKNOWN" {
  if (!cardGeneratedAt || !provenance || provenance.length === 0) {
    return "UNKNOWN";
  }
  for (const dep of provenance) {
    if (!dep.artifact_timestamp) {
      continue; // missing timestamp for this dep — skip rather than fail the whole card
    }
    if (dep.artifact_timestamp > cardGeneratedAt) {
      return "STALE";
    }
  }
  return "FRESH";
}

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
      outcome_attribution_summary?: {
        directly_attributable?: number;
        strongly_supported?: number;
        associated_not_attributable?: number;
        no_outcome_evidence?: number;
        negative_outcome?: number;
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
    dependency_provenance?: DependencyProvenanceEntry[] | null;
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
    outcomeAttributionSummary: raw.outcome_attribution_summary ?? null,
  };
}

async function loadCanonicalAnswerCard(
  publicSlug: string,
  internalKey: string,
  questionId: string,
): Promise<ResearchAnswerCard | null> {
  const paths = getAskIntrinsicIqPaths(internalKey);

  if (!paths) {
    return null;
  }

  const [payload, company, productsAndServices, financialVisuals] =
    await Promise.all([
      readJsonIfExists<RawAnswerCardsPayload>(paths.answerCards),
      getCompanyResearchView(publicSlug),
      getProductsServices(publicSlug),
      getFinancialVisuals(publicSlug),
    ]);

  const raw = payload?.answers.find((entry) => entry.question_id === questionId);

  if (!raw || !company || !artifactCompanyMatches(internalKey, payload?.company_slug, paths.answerCards)) {
    return null;
  }

  // Freshness gate: do not serve a saved card that is older than its own registered dependencies.
  // UNKNOWN is not treated as FRESH — log it but continue (allows serving when provenance is absent
  // on legacy cards that pre-date this schema; remove that permissive path after first full pipeline run).
  const freshnessState = checkAnswerCardFreshness(raw.dependency_provenance, raw.generated_at);
  if (freshnessState === "STALE") {
    logRuntimeIssue("Answer card is stale relative to its registered dependencies — not serving.", {
      companySlug: publicSlug,
      questionId,
      cardGeneratedAt: raw.generated_at,
      staleDependencies: (raw.dependency_provenance ?? []).filter(
        (dep) => dep.artifact_timestamp && raw.generated_at && dep.artifact_timestamp > raw.generated_at,
      ),
    });
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
      companySlug: publicSlug,
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
      companySlug: publicSlug,
      questionId,
      errors,
    });
    return null;
  }

  return finalized;
}

// ─────────────────────────────────────────────────────────────────────────────
// Hybrid Level-3 canary loader (Mission 19)
// ─────────────────────────────────────────────────────────────────────────────

type RawHybridPrecisionFact = {
  metric?: string;
  value?: string;
  period?: string;
  semantic_meaning?: string;
};

type RawHybridAnswer = {
  simple_answer?: string;
  what_evidence_shows?: string[];
  what_may_mean_economically?: string;
  what_is_not_yet_proven?: string;
  what_to_monitor?: string[];
  why_it_matters?: string;
  key_points?: string[];
  deterministic_precision_facts?: RawHybridPrecisionFact[];
};

type RawHybridEntry = {
  question_id?: string;
  answer?: RawHybridAnswer;
  status?: string;
  coverage?: string;
};

type RawHybridPayload = {
  company_slug?: string;
  answers?: Record<string, RawHybridEntry>;
};

function formatPrecisionFact(pf: RawHybridPrecisionFact): string {
  const metric = (pf.metric ?? "").trim();
  const value = (pf.value ?? "").trim();
  const period = (pf.period ?? "").trim();
  if (!metric && !value) return "";
  if (period) return `${metric} (${period}): ${value}`;
  return `${metric}: ${value}`;
}

function buildHybridStructuredSections(
  raw: RawHybridAnswer,
): Array<{ title: string; points: string[] }> {
  const sections: Array<{ title: string; points: string[] }> = [];

  const evidencePoints = cleanPublicList(raw.what_evidence_shows ?? [], { limit: 6 });
  if (evidencePoints.length > 0) {
    sections.push({ title: "What the evidence shows", points: evidencePoints });
  }

  const monitorPoints = cleanPublicList(raw.what_to_monitor ?? [], { limit: 3 });
  if (monitorPoints.length > 0) {
    sections.push({ title: "What to monitor", points: monitorPoints });
  }

  const dpfPoints = (raw.deterministic_precision_facts ?? [])
    .map(formatPrecisionFact)
    .filter(Boolean);
  const cleanedDpf = cleanPublicList(dpfPoints, { limit: 8 });
  if (cleanedDpf.length > 0) {
    sections.push({ title: "Key facts", points: cleanedDpf });
  }

  return sections;
}

// ── Approval registry runtime enforcement ────────────────────────────────────
// Phase 3: Runtime check — pairs must be in the approval registry with a valid,
// non-pending fingerprint match. PENDING_INDEPENDENT_REVIEW is a hard block.
// PENDING_MIGRATION_REVIEW logs a warning but serves (migration grace period).
// Spec: governance/sanitizer_contract.json + governance/approval_registry.json

type ApprovalRecord = {
  fingerprint: string;
  full_artifact_digest?: string | null;
  artifact_identity_version?: string | null;
  status?: string;
};

let _approvalCache: Record<string, ApprovalRecord> | null = null;
let _approvalCacheMtime: number | null = null;

// Phase 3: mtime-based invalidation — revocation effective on next request (not restart-dependent).
// Fails closed on stat error: returns {} so every pair returns APPROVAL_NOT_REGISTERED.
async function loadApprovalRegistry(repoRoot: string): Promise<Record<string, ApprovalRecord>> {
  const registryPath = path.join(repoRoot, "governance", "approval_registry.json");
  let currentMtime: number | null = null;
  try {
    currentMtime = fs.statSync(registryPath).mtimeMs;
  } catch {
    // Registry unreadable — fail closed
    logRuntimeIssue("Approval registry unreadable — all hybrid answers blocked.", { registryPath });
    return {};
  }
  if (_approvalCache !== null && _approvalCacheMtime === currentMtime) {
    return _approvalCache;
  }
  try {
    const data = await readJsonIfExists<{ approvals: Record<string, ApprovalRecord> }>(registryPath);
    _approvalCache = data?.approvals ?? {};
    _approvalCacheMtime = currentMtime;
  } catch {
    _approvalCache = {};
    _approvalCacheMtime = null;
  }
  return _approvalCache;
}

// Mirrors Python json.dumps(sort_keys=True, ensure_ascii=True):
//   - ": " and ", " separators
//   - keys sorted recursively
//   - non-ASCII chars escaped as \uXXXX (Python ensure_ascii=True default)
function _pyJsonStr(s: string): string {
  // Start with JS JSON (handles ", \, control chars) then escape non-ASCII as \uXXXX
  return JSON.stringify(s).replace(/[^\x00-\x7F]/gu, (ch) => {
    const cp = ch.codePointAt(0)!;
    if (cp > 0xffff) {
      const hi = Math.floor((cp - 0x10000) / 0x400) + 0xd800;
      const lo = ((cp - 0x10000) % 0x400) + 0xdc00;
      return `\\u${hi.toString(16).padStart(4, "0")}\\u${lo.toString(16).padStart(4, "0")}`;
    }
    return `\\u${cp.toString(16).padStart(4, "0")}`;
  });
}

function _pyJson(val: unknown): string {
  if (val === null) return "null";
  if (typeof val === "boolean") return val ? "true" : "false";
  if (typeof val === "number") return String(val);
  if (typeof val === "string") return _pyJsonStr(val);
  if (Array.isArray(val)) return "[" + val.map(_pyJson).join(", ") + "]";
  const obj = val as Record<string, unknown>;
  return (
    "{" +
    Object.keys(obj)
      .sort()
      .map((k) => `${_pyJsonStr(k)}: ${_pyJson(obj[k])}`)
      .join(", ") +
    "}"
  );
}

function computeAnswerFingerprint(answer: Record<string, unknown>): string {
  // Mirrors PACP: MD5(json.dumps(answer_minus_dpf, sort_keys=True))[:16]
  const { deterministic_precision_facts: _dpf, ...reduced } = answer;
  return crypto.createHash("md5").update(_pyJson(reduced)).digest("hex").slice(0, 16);
}

function computeFullArtifactDigest(answer: Record<string, unknown>): string {
  // Phase 4: SHA-256 of ALL answer fields including DPFs.
  // Mirrors Python: hashlib.sha256(json.dumps(answer, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
  return crypto.createHash("sha256").update(_pyJson(answer)).digest("hex");
}

// Default next-questions used when a hybrid answer has no corresponding production card yet.
const HYBRID_NEW_FAMILY_NEXT_QUESTIONS = [
  { id: "what-has-management-promised",   questionId: "what-has-management-promised",   title: "What has management promised?",     shortLabel: "Promises" },
  { id: "how-is-capital-allocated",       questionId: "how-is-capital-allocated",       title: "How is capital allocated?",         shortLabel: "Capital" },
  { id: "did-execution-lead-to-outcomes", questionId: "did-execution-lead-to-outcomes", title: "Did execution lead to outcomes?",   shortLabel: "Outcomes" },
] as ResearchAnswerCard["nextQuestions"];

async function loadHybridAnswerCard(
  publicSlug: string,
  internalKey: string,
  questionId: string,
  productionCard: ResearchAnswerCard | null,
): Promise<ResearchAnswerCard | null> {
  const paths = getAskIntrinsicIqPaths(internalKey);
  if (!paths) return null;

  let payload: RawHybridPayload | null = null;
  try {
    payload = await readJsonIfExists<RawHybridPayload>(paths.shadowLevel3HybridAnswers);
  } catch {
    logRuntimeIssue("Hybrid answer artifact could not be read.", { companySlug: publicSlug, questionId });
    return null;
  }

  if (!payload?.answers) return null;

  // Verify company identity matches
  if (payload.company_slug && payload.company_slug !== internalKey) {
    logRuntimeIssue("Hybrid artifact company slug mismatch — not serving.", {
      failure_class: "HYBRID_CROSS_COMPANY_CONTAMINATION",
      requested: internalKey,
      artifact: payload.company_slug,
    });
    return null;
  }

  const entry = payload.answers[questionId];
  if (!entry) return null;

  // Safety gates
  if (entry.status !== "PASS") {
    logRuntimeIssue("Hybrid answer not PASS — production fallback.", { companySlug: publicSlug, questionId, status: entry.status });
    return null;
  }
  if (entry.coverage !== "COMPLETE") {
    logRuntimeIssue("Hybrid answer coverage not COMPLETE — production fallback.", { companySlug: publicSlug, questionId, coverage: entry.coverage });
    return null;
  }

  const raw = entry.answer;
  if (!raw || typeof raw !== "object") return null;

  // Approval registry enforcement (Phase 3 — M35.3)
  const approvals = await loadApprovalRegistry(paths.repoRoot);
  const registryKey = `${internalKey}:${questionId}`;
  const approvalRecord = approvals[registryKey];

  if (!approvalRecord) {
    logRuntimeIssue("Hybrid answer has no approval registry record — production fallback.", {
      failure_class: "APPROVAL_NOT_REGISTERED",
      companySlug: publicSlug,
      questionId,
    });
    return null;
  }

  if (approvalRecord.status === "PENDING_INDEPENDENT_REVIEW") {
    logRuntimeIssue("Hybrid answer approval is PENDING_INDEPENDENT_REVIEW — production fallback.", {
      failure_class: "APPROVAL_PENDING_INDEPENDENT_REVIEW",
      companySlug: publicSlug,
      questionId,
    });
    return null;
  }

  const runtimeFingerprint = computeAnswerFingerprint(raw as Record<string, unknown>);
  if (runtimeFingerprint !== approvalRecord.fingerprint) {
    logRuntimeIssue("Hybrid answer fingerprint mismatch since approval — production fallback.", {
      failure_class: "APPROVAL_FINGERPRINT_MISMATCH",
      companySlug: publicSlug,
      questionId,
      runtimeFingerprint,
      registryFingerprint: approvalRecord.fingerprint,
    });
    return null;
  }

  if (approvalRecord.status === "PENDING_MIGRATION_REVIEW") {
    // Phase 2 (M35.4): Hard block — no indefinite grace period. Must obtain independent re-approval.
    logRuntimeIssue("Hybrid answer approval is PENDING_MIGRATION_REVIEW — production fallback.", {
      failure_class: "APPROVAL_PENDING_MIGRATION_REVIEW",
      companySlug: publicSlug,
      questionId,
    });
    return null;
  }

  // Phase 4: Full-artifact digest check (includes DPFs).
  // If registry has full_artifact_digest, it must match; prevents silent DPF tampering.
  // Legacy approvals without full_artifact_digest log a warning but are not blocked
  // until they complete identity migration (schema_version < 2 entries).
  if (approvalRecord.full_artifact_digest) {
    const runtimeFullDigest = computeFullArtifactDigest(raw as Record<string, unknown>);
    if (runtimeFullDigest !== approvalRecord.full_artifact_digest) {
      logRuntimeIssue("Full-artifact digest mismatch (DPFs or content changed since approval) — production fallback.", {
        failure_class: "FULL_ARTIFACT_DIGEST_MISMATCH",
        companySlug: publicSlug,
        questionId,
        runtimeDigest: runtimeFullDigest,
        registryDigest: approvalRecord.full_artifact_digest,
      });
      return null;
    }
  } else {
    // Legacy approval: no full_artifact_digest recorded. Log warning; serve via legacy fingerprint only.
    logRuntimeIssue("Approval has no full_artifact_digest — serving on legacy fingerprint only. Run --mode approve to migrate.", {
      failure_class: "FULL_ARTIFACT_DIGEST_MISSING",
      companySlug: publicSlug,
      questionId,
    });
  }

  const simpleAnswer = cleanPublicText(raw.simple_answer ?? "");
  if (!simpleAnswer) return null;

  const keyPoints = cleanPublicList(raw.key_points ?? raw.what_evidence_shows ?? [], { limit: 4 });

  const notYetProven = cleanPublicText(raw.what_is_not_yet_proven ?? "");
  const economicMeaning = cleanPublicText(raw.what_may_mean_economically ?? "");
  const whyItMatters = cleanPublicText(raw.why_it_matters ?? economicMeaning);

  const card: ResearchAnswerCard = {
    // Identity — from production when available, synthesized for new question families
    id: productionCard?.id ?? `answer-${questionId}`,
    questionId: productionCard?.questionId ?? questionId,
    title: productionCard?.title ?? questionId,
    questionType: productionCard?.questionType ?? "progression",
    // Navigation — from production when available, default set for new families
    nextQuestions: productionCard?.nextQuestions ?? HYBRID_NEW_FAMILY_NEXT_QUESTIONS,
    // Content — from hybrid
    simpleAnswer,
    whyItMatters: whyItMatters || null,
    detailedExplanation: economicMeaning,
    keyPoints,
    structuredSections: buildHybridStructuredSections(raw),
    // Evidence disclosure: first few what_evidence_shows items
    evidenceSummary: cleanPublicList(raw.what_evidence_shows ?? [], { limit: 4 })
      .map((detail, index) => ({
        label: index === 0 ? "Evidence summary" : `Supporting point ${index}`,
        detail,
        evidenceStatus: "partial" as const,
      }))
      .filter((item) => item.detail),
    // Uncertainty — from what_is_not_yet_proven
    uncertaintyNote: {
      label: notYetProven ? "What is not yet proven" : (productionCard?.uncertaintyNote.label ?? "Uncertainty note"),
      detail: notYetProven || (productionCard?.uncertaintyNote.detail ?? ""),
      evidenceStatus: "partial",
    },
    // Fields not in hybrid — empty / null
    productsAndServices: [],
    businessJourney: null,
    financialVisualRefs: [],
    customerRoles: null,
    revenueFlow: null,
    progression: null,
    interpretation: null,
    answerStatus: "supported",
    generatedAt: new Date().toISOString(),
  };

  const errors = validateResearchAnswerCard(card);
  if (errors.length > 0) {
    logRuntimeIssue("Hybrid answer card failed runtime validation — production fallback.", {
      companySlug: publicSlug,
      questionId,
      errors,
    });
    return null;
  }

  return card;
}

export async function getResearchAnswerCard(
  publicSlug: string,
  questionId: string,
): Promise<ResearchAnswerCard | null> {
  const result = await getResearchAnswerCardWithSource(publicSlug, questionId);
  return result?.card ?? null;
}

export async function getResearchAnswerCardWithSource(
  publicSlug: string,
  questionId: string,
): Promise<ResearchAnswerCardWithSource | null> {
  if (!isValidRouteSegment(publicSlug) || !isValidRouteSegment(questionId)) {
    return null;
  }

  const internalKey = await resolveInternalKey(publicSlug);
  if (!internalKey) {
    return null;
  }

  const [productionCard, company] = await Promise.all([
    loadCanonicalAnswerCard(publicSlug, internalKey, questionId),
    getCompanyResearchView(publicSlug),
  ]);

  // Canary path: eligible → serve hybrid (productionCard may be null for new question families)
  const canaryConfig = getCanaryConfig();
  if (isCanaryEligible(canaryConfig, internalKey, questionId)) {
    const hybridCard = await loadHybridAnswerCard(publicSlug, internalKey, questionId, productionCard ?? null);
    if (hybridCard) {
      logCanaryRender(publicSlug, questionId, "HYBRID_CANARY", null);
      return { card: hybridCard, source: "HYBRID_CANARY" };
    }
    // Hybrid failed — fall through to production
    logCanaryRender(publicSlug, questionId, "PRODUCTION_FALLBACK", "hybrid_load_failed");
  }

  if (productionCard) {
    return { card: productionCard, source: "PRODUCTION_FALLBACK" };
  }

  if (company) {
    const unavailableCard = await buildUnavailableResearchAnswerCard(publicSlug, questionId, company);
    if (unavailableCard) {
      return { card: unavailableCard, source: "PRODUCTION_FALLBACK" };
    }
  }

  return null;
}

function logCanaryRender(
  companySlug: string,
  questionId: string,
  source: AnswerSource,
  fallbackReason: string | null,
) {
  console.log(
    JSON.stringify({
      event: "prometheus_canary_render",
      companySlug,
      questionId,
      source,
      fallbackReason,
      timestamp: new Date().toISOString(),
    }),
  );
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
