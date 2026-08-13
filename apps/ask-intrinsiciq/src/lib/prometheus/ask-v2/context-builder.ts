import type { RawSources } from "../answer-builders";
import type {
  AskConfidenceLevel,
  AskContextV2,
  AskPlan,
  AskSourceReference,
  AskIntentId,
} from "./answer-contracts";
import { selectAskContextEvidence } from "./evidence-selector";

export function buildAskContextV2(sources: RawSources, askPlan: AskPlan): AskContextV2 {
  const selected = selectAskContextEvidence(sources, askPlan);
  const evidence = selected.evidence.slice(0, askPlan.evidenceBudget);
  const rawFallbackUsed = selected.rawFallbackUsed || askPlan.requiresRawDocumentFallback;
  const progression = uniqueStrings(selected.progression).slice(0, askPlan.evidenceBudget);
  const unresolved = uniqueStrings(selected.unresolved).slice(0, askPlan.evidenceBudget);
  const rawNumbers = uniqueStrings(selected.rawNumbers).slice(0, askPlan.evidenceBudget);
  const sourcesUsed = uniqueSourceKeys(selected.sources);
  const confidence = deriveConfidence({
    plan: askPlan,
    evidenceCount: evidence.length,
    progressionCount: progression.length,
    unresolvedCount: unresolved.length,
    rawFallbackUsed,
    sourcesUsed,
  });

  return {
    plan: askPlan,
    canonicalSourcesUsed: sourcesUsed,
    evidence,
    progression,
    rawNumbers,
    unresolved,
    sources: selected.sources.slice(0, askPlan.evidenceBudget).map(toSourceReference),
    confidence,
    rawFallbackUsed,
    contextSize: estimateContextSize(evidence, progression, rawNumbers, unresolved),
    limitations: buildLimitations(askPlan, confidence, rawFallbackUsed, evidence.length),
  };
}

export function buildAskV2Summary(context: AskContextV2) {
  const primaryLabel = intentLabel(context.plan.primaryIntent);
  return {
    conclusion: summarizeConclusion(context),
    whatChanged: summarizeChange(context),
    whyItChanged: summarizeWhy(context),
    whyItMatters: summarizeWhyItMatters(context),
    convictionImpact: summarizeConvictionImpact(context),
    evidence: context.evidence,
    rawNumbers: context.rawNumbers,
    unresolved: context.unresolved,
    confidence: context.confidence,
    sources: context.sources,
    followUpQuestions: buildFollowUps(context, primaryLabel),
    askDiagnostics: {
      detectedIntent: context.plan.primaryIntent,
      canonicalSourcesUsed: context.canonicalSourcesUsed,
      rawFallbackUsed: context.rawFallbackUsed,
      evidenceCount: context.evidence.length,
      progressionUsed: context.plan.requiresProgression || context.progression.length > 0,
      contextSize: context.contextSize,
      confidence: context.confidence,
      validationStatus: "pass" as const,
    },
  };
}

function summarizeConclusion(context: AskContextV2) {
  if (context.evidence.length > 0) {
    return context.evidence[0].detail;
  }
  return "Evidence is not yet sufficient to form a stronger conclusion.";
}

function summarizeChange(context: AskContextV2) {
  if (context.progression.length > 0) {
    return context.progression.slice(0, 2).join(" ");
  }
  if (context.rawFallbackUsed) {
    return "Canonical evidence was thin, so the answer falls back to the best available raw disclosure evidence.";
  }
  return "No material progression evidence was available.";
}

function summarizeWhy(context: AskContextV2) {
  if (context.evidence.length > 1) {
    return context.evidence.slice(1, 3).map((item) => item.detail).join(" ");
  }
  return context.limitations[0] || "The available evidence is still limited.";
}

function summarizeWhyItMatters(context: AskContextV2) {
  if (context.plan.requiresFinancialValues) {
    return "This matters because the question changes how cash, returns, or per-share economics should be read.";
  }
  if (context.plan.requiresInvestorLens) {
    return "This matters because investor conviction should move only when the evidence really changes.";
  }
  if (context.plan.requiresProgression) {
    return "This matters because investors need the path, not just the latest snapshot.";
  }
  return "This matters because it helps explain the business more clearly.";
}

function summarizeConvictionImpact(context: AskContextV2): "strengthened" | "weakened" | "unchanged" | "unclear" {
  if (context.evidence.length === 0) return "unclear" as const;
  if (context.rawFallbackUsed) return "unclear" as const;
  if (context.plan.primaryIntent === "management_commitments" || context.plan.primaryIntent === "projects" || context.plan.primaryIntent === "capacity") {
    return context.progression.some((item) => /delivered|operational|commissioned|strengthened/i.test(item))
      ? "strengthened"
      : "unchanged";
  }
  if (context.plan.primaryIntent === "risk") {
    return context.evidence.some((item) => /medium|high|persistent|worsening/i.test(item.detail)) ? "weakened" : "unchanged";
  }
  if (context.plan.primaryIntent === "capital_allocation") {
    return context.evidence.some((item) => /return|outcome|payoff|strengthened/i.test(item.detail))
      ? "strengthened"
      : "unchanged";
  }
  return "unchanged";
}

function buildFollowUps(context: AskContextV2, primaryLabel: string) {
  const followUps = [
    context.plan.primaryIntent === "management_commitments"
      ? "Which commitments remain unresolved?"
      : null,
    context.plan.primaryIntent === "projects" || context.plan.primaryIntent === "capacity"
      ? "Did the execution create visible economic return?"
      : null,
    context.plan.primaryIntent === "risk"
      ? "What evidence would reduce the main risk?"
      : null,
    context.plan.primaryIntent === "capital_allocation"
      ? "What did the capital deployment actually produce?"
      : null,
    context.plan.primaryIntent === "investor_lens"
      ? "What evidence would change the lens most?"
      : null,
  ].filter((item): item is string => Boolean(item));

  if (followUps.length === 0) {
    followUps.push(`What should I investigate next about ${primaryLabel.toLowerCase()}?`);
  }
  return uniqueStrings(followUps).slice(0, 3);
}

function deriveConfidence(args: {
  plan: AskPlan;
  evidenceCount: number;
  progressionCount: number;
  unresolvedCount: number;
  rawFallbackUsed: boolean;
  sourcesUsed: AskSourceReference["sourceKey"][];
}): AskConfidenceLevel {
  const { plan, evidenceCount, progressionCount, unresolvedCount, rawFallbackUsed, sourcesUsed } = args;
  if (rawFallbackUsed && evidenceCount < 2) return "low";
  if (evidenceCount === 0) return "insufficient";
  if (plan.requiresProgression && progressionCount === 0) return "low";
  if (plan.requiresInvestorLens && sourcesUsed.length < 2) return "low";
  if (unresolvedCount > 0 && evidenceCount < 3) return "medium";
  if (evidenceCount >= 3 && progressionCount >= 1) return "high";
  return "medium";
}

function buildLimitations(plan: AskPlan, confidence: AskConfidenceLevel, rawFallbackUsed: boolean, evidenceCount: number) {
  const limitations: string[] = [...plan.limitations];
  if (rawFallbackUsed) limitations.push("Raw-document fallback was needed.");
  if (confidence === "insufficient") limitations.push("Evidence is too thin to support a strong conclusion.");
  if (evidenceCount < 2) limitations.push("Very few evidence items were available.");
  return uniqueStrings(limitations);
}

function estimateContextSize(
  evidence: Array<{ detail: string }>,
  progression: string[],
  rawNumbers: string[],
  unresolved: string[],
) {
  return evidence.reduce((count, item) => count + item.detail.length, 0) + progression.join(" ").length + rawNumbers.join(" ").length + unresolved.join(" ").length;
}

function uniqueStrings(items: string[]) {
  return Array.from(new Set(items.map((item) => item.trim()).filter(Boolean)));
}

function uniqueSourceKeys(items: AskSourceReference[]) {
  return Array.from(
    new Set(items.map((item) => item.sourceKey).filter((key): key is Exclude<AskSourceReference["sourceKey"], "raw_document_fallback"> => key !== "raw_document_fallback")),
  );
}

function toSourceReference(item: AskSourceReference) {
  return {
    sourceKey: item.sourceKey,
    label: item.label,
    period: item.period,
    reference: item.reference,
  };
}

function intentLabel(intent: AskIntentId) {
  switch (intent) {
    case "management_commitments":
      return "management commitments";
    case "financial_performance":
      return "financial performance";
    case "financial_progression":
      return "financial progression";
    case "owner_earnings":
      return "owner earnings";
    case "working_capital":
      return "working capital";
    case "per_share_compounding":
      return "per-share compounding";
    case "management_quality":
      return "management quality";
    case "projects":
      return "projects";
    case "capacity":
      return "capacity";
    case "risk":
      return "risk";
    case "management_commentary":
      return "management commentary";
    case "capital_allocation":
      return "capital allocation";
    case "investor_lens":
      return "investor lens";
    case "committee_view":
      return "committee view";
    case "disagreement":
      return "disagreement";
    case "thesis_change":
      return "thesis change";
    case "unresolved_questions":
      return "unresolved questions";
    case "diligence":
      return "diligence";
    case "raw_document_fact":
      return "raw document fact";
    case "cross_domain":
      return "cross-domain question";
    default:
      return "question";
  }
}
