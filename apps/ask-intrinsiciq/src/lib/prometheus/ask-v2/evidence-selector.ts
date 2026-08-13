import type { RawSources } from "../answer-builders";
import type {
  AskContextV2,
  AskEvidenceItem,
  AskPlan,
  AskSourceReference,
  CanonicalSourceKey,
} from "./answer-contracts";

type RawDiscoveryBundle = {
  period?: string;
  year?: string;
  promiseDiscoveries?: unknown;
  projectDiscoveries?: unknown;
  capacityDiscoveries?: unknown;
  riskDiscoveries?: unknown;
  commentaryDiscoveries?: unknown;
  capitalAllocationDiscoveries?: unknown;
  initiativeDiscoveries?: unknown;
  [key: string]: unknown;
};

type SelectionState = {
  evidence: AskEvidenceItem[];
  sources: AskSourceReference[];
  progression: string[];
  rawNumbers: string[];
  unresolved: string[];
  rawFallbackUsed: boolean;
};

const MAX_EVIDENCE_PER_INTENT = 4;

export function selectAskContextEvidence(sources: RawSources, plan: AskPlan): SelectionState {
  const state: SelectionState = {
    evidence: [],
    sources: [],
    progression: [],
    rawNumbers: [],
    unresolved: [],
    rawFallbackUsed: false,
  };

  for (const sourceKey of plan.canonicalSourceKeys) {
    switch (sourceKey) {
      case "managementCommitments":
        pushCommitmentEvidence(state, sources.managementCommitments);
        break;
      case "projectAssessments":
      case "projectTimelines":
        pushProjectEvidence(state, sources.projectAssessments, sources.projectTimelines);
        break;
      case "capacityAssessments":
      case "capacityTimelines":
        pushCapacityEvidence(state, sources.capacityAssessments, sources.capacityTimelines);
        break;
      case "riskAssessments":
      case "riskTimelines":
        pushRiskEvidence(state, sources.riskAssessments, sources.riskTimelines, sources.riskEvolution);
        break;
      case "commentaryAssessments":
      case "commentaryTimelines":
        pushCommentaryEvidence(state, sources.commentaryAssessments, sources.commentaryTimelines, sources.commentaryThemes);
        break;
      case "managementQualitySummary":
      case "managementQualityDimensions":
        pushManagementQualityEvidence(state, sources.managementQualitySummary, sources.managementQualityDimensions);
        break;
      case "capitalAllocationOutcomes":
      case "capitalAllocationTimelines":
      case "capitalAllocationRoi":
        pushCapitalAllocationEvidence(state, sources.capitalAllocationOutcomes, sources.capitalAllocationTimelines, sources.capitalAllocationRoi);
        break;
      case "financialTruthPack":
      case "ownerEarningsBridge":
      case "workingCapitalQuality":
      case "perShareCompounding":
        pushFinancialEvidence(state, sources.truthPack, sources.ownerEarningsBridge, sources.workingCapitalQuality, sources.perShareCompounding);
        break;
      case "buffettAnalysis":
      case "grahamAnalysis":
      case "fisherAnalysis":
      case "mungerAnalysis":
      case "lynchAnalysis":
        pushInvestorLensEvidence(state, sourceKey, sources);
        break;
      case "committeeSynthesis":
      case "committeeBriefQa":
      case "panelRunSummary":
        pushCommitteeEvidence(state, sources.committeeSynthesis, sources.committeeBriefQa, sources.panelRunSummary);
        break;
      case "pcim":
        pushBusinessEvidence(state, sources.pcim);
        break;
      case "rawDiscoveryBundles":
        pushRawDiscoveryEvidence(state, sources.rawDiscoveryBundles as RawDiscoveryBundle[] | undefined, plan);
        break;
      default:
        break;
    }
    if (state.evidence.length >= MAX_EVIDENCE_PER_INTENT && plan.primaryIntent !== "cross_domain") {
      break;
    }
  }

  return state;
}

function pushBusinessEvidence(state: SelectionState, payload: Record<string, unknown> | null | undefined) {
  const businessModel = (((payload || {}) as any).business_understanding || {}).latest_business_view?.business_model || {};
  push(state, "Business model", pickString(businessModel, "business_summary", "business_model"), "pcim");
  push(state, "Positioning", pickString(businessModel, "competitive_position_summary", "value_creation"), "pcim");
}

function pushFinancialEvidence(
  state: SelectionState,
  truthPack: Record<string, unknown> | null | undefined,
  bridge: Record<string, unknown> | null | undefined,
  workingCapital: Record<string, unknown> | null | undefined,
  perShare: Record<string, unknown> | null | undefined,
) {
  push(state, "Financial truth", pickString(truthPack, "summary", "financial_summary"), "financialTruthPack");
  push(state, "Owner earnings", pickString(bridge, "summary", "owner_earnings_summary"), "ownerEarningsBridge");
  push(state, "Working capital", pickString(workingCapital, "working_capital_intensity_status", "cash_strain_risk"), "workingCapitalQuality");
  push(state, "Per-share economics", pickString(perShare, "summary", "per_share_summary"), "perShareCompounding");
  const precision = firstString((truthPack as any)?.precision_limits);
  if (precision) {
    state.unresolved.push(precision);
  }
}

function pushCommitmentEvidence(state: SelectionState, payload: Record<string, unknown> | null | undefined) {
  const commitments = ensureArray((payload as any)?.commitments).filter(Boolean) as Record<string, unknown>[];
  const sorted = commitments.slice().sort((a, b) => scorePriority(a) - scorePriority(b));
  for (const commitment of sorted.slice(0, 3)) {
    const topic = pickString(commitment, "topic", "category") || "Commitment";
    const normalized = pickString(commitment, "normalized_commitment", "delivery_assessment") || "";
    const status = pickString(commitment, "status") || "";
    const timeframe = pickString(commitment, "expected_timeframe", "announcement_period") || "";
    const detail = [normalized, status ? `Status: ${status}.` : "", timeframe ? `Timeframe: ${timeframe}.` : ""].filter(Boolean).join(" ");
    push(state, topic, detail, "managementCommitments");
    const progression = buildProgression(commitment);
    if (progression) state.progression.push(progression);
  }
}

function pushProjectEvidence(
  state: SelectionState,
  assessments: Record<string, unknown> | null | undefined,
  timelines: Record<string, unknown> | null | undefined,
) {
  const items = ensureArray((assessments as any)?.assessments) as Record<string, unknown>[];
  const ordered = items
    .map((item) => ({ item, score: projectScore(item) }))
    .sort((a, b) => b.score - a.score)
    .slice(0, 3);
  for (const { item } of ordered) {
    const name = pickString(item, "project_name", "normalized_name") || "Project";
    const execution = pickString(item, "execution_summary", "execution_status") || "";
    const impact = pickString(item, "observed_business_effect", "observed_financial_effect") || "";
    const conviction = pickString(item, "conviction_impact") || "";
    push(state, name, [execution, impact, conviction ? `Conviction: ${conviction}.` : ""].filter(Boolean).join(" "), "projectAssessments");
    state.unresolved.push(...ensureArray(item.unresolved_questions).map(String));
    const timelineState = pickString(timelines as any, "current_state", "coverage_status");
    if (timelineState) state.progression.push(`${name}: ${timelineState}`);
  }
}

function pushCapacityEvidence(
  state: SelectionState,
  assessments: Record<string, unknown> | null | undefined,
  timelines: Record<string, unknown> | null | undefined,
) {
  const items = ensureArray((assessments as any)?.assessments) as Record<string, unknown>[];
  const ordered = items
    .map((item) => ({ item, score: capacityScore(item) }))
    .sort((a, b) => b.score - a.score)
    .slice(0, 3);
  for (const { item } of ordered) {
    const name = pickString(item, "capacity_name", "normalized_name") || "Capacity";
    const utilization = pickString(item, "utilization_status", "execution_status") || "";
    const impact = pickString(item, "observed_business_effect", "observed_financial_effect") || "";
    push(state, name, [utilization ? `Utilization: ${utilization}.` : "", impact].filter(Boolean).join(" "), "capacityAssessments");
    state.unresolved.push(...ensureArray(item.unresolved_questions).map(String));
    const timelineState = pickString(timelines as any, "current_state", "coverage_status");
    if (timelineState) state.progression.push(`${name}: ${timelineState}`);
  }
}

function pushRiskEvidence(
  state: SelectionState,
  assessments: Record<string, unknown> | null | undefined,
  timelines: Record<string, unknown> | null | undefined,
  evolution: Record<string, unknown> | null | undefined,
) {
  const items = ensureArray((assessments as any)?.assessments || (timelines as any)?.timelines || (evolution as any)?.risks) as Record<string, unknown>[];
  for (const item of items.slice(0, 3)) {
    const name = pickString(item, "risk_name", "normalized_risk", "risk") || "Risk";
    const status = pickString(item, "latest_severity", "current_status", "severity") || "";
    const mechanism = pickString(item, "risk_mechanism", "progression_summary") || "";
    push(state, name, [status ? `Latest severity: ${status}.` : "", mechanism].filter(Boolean).join(" "), "riskAssessments");
    state.unresolved.push(...ensureArray(item.unresolved_questions).map(String));
    const progression = pickString(item, "progression_summary");
    if (progression) state.progression.push(`${name}: ${progression}`);
  }
}

function pushCommentaryEvidence(
  state: SelectionState,
  assessments: Record<string, unknown> | null | undefined,
  timelines: Record<string, unknown> | null | undefined,
  themes: Record<string, unknown> | null | undefined,
) {
  const items = ensureArray((assessments as any)?.assessments || (timelines as any)?.timelines || (themes as any)?.themes) as Record<string, unknown>[];
  for (const item of items.slice(0, 3)) {
    const theme = pickString(item, "normalized_theme", "theme_name", "theme") || "Commentary";
    const emphasis = pickString(item, "current_emphasis", "progression_summary") || "";
    const position = pickString(item, "current_position", "current_state") || "";
    push(state, theme, [emphasis, position ? `Position: ${position}.` : ""].filter(Boolean).join(" "), "commentaryAssessments");
    const progression = pickString(item, "progression_summary");
    if (progression) state.progression.push(`${theme}: ${progression}`);
  }
}

function pushManagementQualityEvidence(
  state: SelectionState,
  summary: Record<string, unknown> | null | undefined,
  dimensions: Record<string, unknown> | null | undefined,
) {
  const overall = pickString(summary, "overall_view", "overall_direction", "investor_implication") || "";
  const strongest = pickString(summary, "strongest_dimension") || "";
  const weakest = pickString(summary, "weakest_dimension") || "";
  push(state, "Management quality", [overall, strongest ? `Strongest: ${strongest}.` : "", weakest ? `Weakest: ${weakest}.` : ""].filter(Boolean).join(" "), "managementQualitySummary");
  const dims = ensureArray((dimensions as any)?.dimensions) as Record<string, unknown>[];
  for (const dim of dims.slice(0, 2)) {
    const name = pickString(dim, "dimension") || "Dimension";
    const assessment = pickString(dim, "assessment", "direction") || "";
    push(state, name, assessment, "managementQualityDimensions");
  }
  state.progression.push(...uniqueStrings(ensureArray((summary as any)?.what_strengthened_conviction).map(String)).slice(0, 2));
}

function pushCapitalAllocationEvidence(
  state: SelectionState,
  outcomes: Record<string, unknown> | null | undefined,
  timelines: Record<string, unknown> | null | undefined,
  roiLedger: Record<string, unknown> | null | undefined,
) {
  const items = ensureArray((outcomes as any)?.outcomes || (outcomes as any)?.items || (roiLedger as any)?.entries || (timelines as any)?.timeline) as Record<string, unknown>[];
  for (const item of items.slice(0, 3)) {
    const label = pickString(item, "title", "objective", "capital_use", "investment_type") || "Capital allocation";
    const outcome = pickString(item, "outcome", "assessment", "execution_summary", "return_summary") || "";
    push(state, label, outcome, "capitalAllocationOutcomes");
    state.unresolved.push(...ensureArray(item.unresolved_questions).map(String));
    const progression = pickString(item, "progression_summary", "why_it_matters");
    if (progression) state.progression.push(`${label}: ${progression}`);
  }
}

function pushInvestorLensEvidence(state: SelectionState, sourceKey: CanonicalSourceKey, sources: RawSources) {
  const analysis = (sources as any)[sourceKey] as Record<string, unknown> | null | undefined;
  const assessment = ((analysis as any)?.assessment || {}) as Record<string, unknown>;
  const keyFindings = ensureArray((analysis as any)?.key_findings).map(String);
  const redFlags = ensureArray((analysis as any)?.red_flags).map(String);
  const uncertainties = ensureArray((analysis as any)?.open_uncertainties).map(String);
  const summary = firstString(Object.values(assessment).map((item) => (typeof item === "string" ? item : "")));
  push(state, sourceKey.replace("Analysis", " lens"), [summary, keyFindings[0], redFlags[0]].filter(Boolean).join(" "), sourceKey);
  if (keyFindings[1]) state.progression.push(keyFindings[1]);
  state.unresolved.push(...uncertainties.slice(0, 2));
}

function pushCommitteeEvidence(
  state: SelectionState,
  synthesis: Record<string, unknown> | null | undefined,
  briefQa: Record<string, unknown> | null | undefined,
  panelRunSummary: Record<string, unknown> | null | undefined,
) {
  const committee = (synthesis as any) || {};
  const overall = pickString(committee, "committee_summary", "overall_committee_view") || "";
  const direction = pickString(committee, "committee_direction", "committee_view") || "";
  const strength = pickString(committee, "consensus_strength") || "";
  push(state, "Committee view", [overall, direction, strength ? `Consensus: ${strength}.` : ""].filter(Boolean).join(" "), "committeeSynthesis");
  const questions = ensureArray((committee as any)?.top_diligence_questions || (committee as any)?.investigation_questions).map(String);
  state.unresolved.push(...questions.slice(0, 3));
  const qaStatus = pickString(briefQa, "status", "qa_mode") || "";
  if (qaStatus) state.progression.push(`Brief QA: ${qaStatus}`);
  const panelStatus = pickString(panelRunSummary, "overall_status", "status") || "";
  if (panelStatus) state.progression.push(`Panel: ${panelStatus}`);
}

function pushRawDiscoveryEvidence(
  state: SelectionState,
  bundles: RawDiscoveryBundle[] | undefined,
  plan: AskPlan,
) {
  if (!bundles || bundles.length === 0) return;
  const fileKey = rawDiscoveryKeyForIntent(plan.primaryIntent);
  for (const bundle of bundles.slice(0, 3)) {
    const raw = (bundle as any)[fileKey];
    const rows = ensureArray(raw) as Record<string, unknown>[];
    for (const row of rows.slice(0, 2)) {
      const chunk = pickString(row, "chunk", "text", "excerpt");
      const page = pickString(row, "page", "page_number");
      const query = ensureArray(row.matched_queries).map(String)[0] || "";
      if (!chunk) continue;
      state.rawFallbackUsed = true;
      push(state, `Raw evidence${page ? ` p.${page}` : ""}`, query ? `${query}: ${truncate(chunk, 220)}` : truncate(chunk, 220), "raw_document_fallback", String(bundle.period || bundle.year || "").trim() || undefined);
    }
  }
}

function rawDiscoveryKeyForIntent(intent: string) {
  switch (intent) {
    case "management_commitments":
      return "promiseDiscoveries";
    case "projects":
      return "projectDiscoveries";
    case "capacity":
      return "capacityDiscoveries";
    case "risk":
      return "riskDiscoveries";
    case "management_commentary":
      return "commentaryDiscoveries";
    case "capital_allocation":
      return "capitalAllocationDiscoveries";
    default:
      return "promiseDiscoveries";
  }
}

function push(state: SelectionState, label: string, detail: string | null | undefined, sourceKey: AskEvidenceItem["sourceKey"], period?: string) {
  const cleaned = normalize(detail);
  if (!cleaned) return;
  state.evidence.push({ label, detail: cleaned, sourceKey, period });
  state.sources.push({ label, sourceKey, period });
}

function buildProgression(item: Record<string, unknown>) {
  const normalized = pickString(item, "normalized_commitment", "normalized_name", "project_name", "capacity_name");
  const status = pickString(item, "status", "current_status", "execution_status", "utilization_status");
  if (!normalized && !status) return "";
  return [normalized, status ? `Latest status: ${status}.` : ""].filter(Boolean).join(" ");
}

function scorePriority(item: Record<string, unknown>) {
  const priority = pickString(item, "priority");
  if (!priority) return 1;
  const value = priority.toLowerCase();
  if (value.includes("high")) return 0;
  if (value.includes("medium")) return 1;
  return 2;
}

function projectScore(item: Record<string, unknown>) {
  const status = pickString(item, "execution_status", "current_status") || "";
  const conviction = pickString(item, "conviction_impact") || "";
  const order: Record<string, number> = { operational: 4, commissioned: 3, partially_operational: 2, delayed: 1, paused: 0 };
  return (order[status] ?? 0) + (conviction === "strengthened" ? 2 : conviction === "weakened" ? 0 : 1);
}

function capacityScore(item: Record<string, unknown>) {
  const utilization = pickString(item, "utilization_status", "current_status") || "";
  const order: Record<string, number> = { materially_utilized: 4, operational: 3, ramping: 2, commissioned: 1, underutilized: 0 };
  return order[utilization] ?? 1;
}

function pickString(item: Record<string, unknown> | null | undefined, ...keys: string[]) {
  for (const key of keys) {
    const value = (item as any)?.[key];
    if (typeof value === "string" && value.trim().length > 0) {
      return value.trim();
    }
  }
  return "";
}

function ensureArray(value: unknown) {
  return Array.isArray(value) ? value : [];
}

function firstString(values: unknown) {
  if (typeof values === "string") {
    return values.trim();
  }
  if (!Array.isArray(values)) {
    return "";
  }
  for (const value of values) {
    if (typeof value === "string" && value.trim().length > 0) return value.trim();
  }
  return "";
}

function normalize(value: string | null | undefined) {
  return (value || "").replace(/\s+/g, " ").trim();
}

function truncate(value: string, limit: number) {
  const text = normalize(value);
  return text.length <= limit ? text : `${text.slice(0, limit - 1).trimEnd()}…`;
}

function uniqueStrings(items: string[]) {
  return Array.from(new Set(items.map((item) => item.trim()).filter(Boolean)));
}
