import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import type { ResearchAnswerCard } from "@/src/types";
import { readJsonIfExists } from "@/src/lib/prometheus/read-json";
import { resolveInternalKey } from "@/src/lib/ask-intrinsiciq/company-discovery";
import { cleanPublicList, cleanPublicText } from "@/src/lib/ask-intrinsiciq/presentation";
import { getAskIntrinsicIqPaths, isValidRouteSegment } from "@/src/lib/ask-intrinsiciq/paths";
import { validateResearchAnswerCard } from "@/src/lib/ask-intrinsiciq/validate-runtime-view";

function logRuntimeIssue(message: string, detail?: unknown) {
  console.error(`[Ask IntrinsicIQ] ${message}`, detail);
}

// Approved hybrid answer loader
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

export function computeAnswerFingerprint(answer: Record<string, unknown>): string {
  // Mirrors PACP: MD5(json.dumps(answer_minus_dpf, sort_keys=True))[:16]
  const { deterministic_precision_facts: _dpf, ...reduced } = answer;
  return crypto.createHash("md5").update(_pyJson(reduced)).digest("hex").slice(0, 16);
}

export function computeFullArtifactDigest(answer: Record<string, unknown>): string {
  // Phase 4: SHA-256 of ALL answer fields including DPFs.
  // Mirrors Python: hashlib.sha256(json.dumps(answer, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
  return crypto.createHash("sha256").update(_pyJson(answer)).digest("hex");
}

// Placeholder next-questions required by the card type; the Cockpit has its own navigation and ignores them.
const HYBRID_NEXT_QUESTIONS = [
  { id: "what-has-management-promised",   questionId: "what-has-management-promised",   title: "What has management promised?",     shortLabel: "Promises" },
  { id: "how-is-capital-allocated",       questionId: "how-is-capital-allocated",       title: "How is capital allocated?",         shortLabel: "Capital" },
  { id: "did-execution-lead-to-outcomes", questionId: "did-execution-lead-to-outcomes", title: "Did execution lead to outcomes?",   shortLabel: "Outcomes" },
] as ResearchAnswerCard["nextQuestions"];

async function loadHybridAnswerCard(
  publicSlug: string,
  internalKey: string,
  questionId: string,
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

  if (approvalRecord.status === "REVOKED") {
    logRuntimeIssue("Hybrid answer approval is REVOKED — production fallback.", {
      failure_class: "APPROVAL_REVOKED",
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
    id: `answer-${questionId}`,
    questionId: questionId,
    title: questionId,
    questionType: "progression",
    // Navigation — from production when available, default set for new families
    nextQuestions: HYBRID_NEXT_QUESTIONS,
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
      label: notYetProven ? "What is not yet proven" : "Uncertainty note",
      detail: notYetProven || "",
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

/**
 * The approved-answer gate for the Cockpit. An answer is served only if it is PASS/COMPLETE, has an approval record
 * that is not pending or revoked, its fingerprint and full-artifact digest still match, and the customer-facing
 * text passes runtime validation. Anything else returns null (fail closed). There is no rollout flag: approval is
 * the only switch.
 */
export async function getApprovedHybridCard(publicSlug: string, questionId: string): Promise<ResearchAnswerCard | null> {
  if (!isValidRouteSegment(publicSlug) || !isValidRouteSegment(questionId)) return null;
  const internalKey = await resolveInternalKey(publicSlug);
  if (!internalKey) return null;
  return loadHybridAnswerCard(publicSlug, internalKey, questionId);
}
