import type { ProgressionInsight } from "@/src/types/progression";
import type { ResearchAnswerCard } from "@/src/types/research-answer";
import type { ResearchAnswer } from "@/src/types/research";
import type { QuestionPresentationType } from "@/src/types/question-presentation";

const LENS_PREFIXES = [
  /^Business model:\s*/i,
  /^Competitive position:\s*/i,
  /^The available evidence includes\s*/i,
  /^Receivables and working-capital dynamics:\s*/i,
];

const PUBLIC_NOISE_PATTERNS = [
  /company memory/i,
  /company-memory/i,
  /available evidence summary/i,
  /source set summaries?/i,
  /saved analyst outputs/i,
  /compact financial inputs/i,
  /committee-level output/i,
  /committee level output/i,
  /source_artifact/i,
  /source_item_id/i,
  /evidence_ids?/i,
  /evidence_map/i,
  /source chunk/i,
  /input pack/i,
  /companies\/[^\s]+/i,
  /source lineage/i,
  /raw artifact/i,
  /\bpcim\b/i,
  /\bcim\b/i,
  /\bllm\b/i,
  /\bpipeline\b/i,
  /\bartifact(s)?\b/i,
  /\bschema\b/i,
  /\bcanonical\b/i,
];

const PUBLIC_MALFORMED_PATTERNS = [
  /\b(?:in|on|for|of|at|to|with|from|by)\s*;/i,
  /\bdescribed as [^.;]{0,80}\b(?:in|on|for|of|at|to|with|from|by)\s*;/i,
];

export function prepareLensBulletForDisplay(text: string): string {
  const normalized = normalizeDisplayText(text);
  const withoutPrefix = stripKnownPrefixes(normalized, LENS_PREFIXES);
  const softened = withoutPrefix
    .replace(/^however,\s*/i, "")
    .replace(/\s+/g, " ")
    .trim();

  return truncateWords(softened, 24);
}

export function prepareFlowStepForDisplay(text: string): string {
  const normalized = normalizeDisplayText(text)
    .replace(/^The business appears to\s*/i, "")
    .replace(/^The company then appears to\s*/i, "")
    .replace(/^Delivery appears to\s*/i, "")
    .replace(/^Systems or subsystems are then\s*/i, "")
    .replace(/^Billing appears\s*/i, "Billing appears ")
    .replace(/^Cash conversion can\s*/i, "Cash conversion can ")
    .trim();

  return truncateWords(normalized, 22);
}

export function prepareFlowLabelForDisplay(label: string): string {
  const normalized = normalizeDisplayText(label)
    .replace(/\bor\b/gi, "")
    .replace(/\bagainst\b/gi, "")
    .replace(/\slater$/i, "")
    .replace(/\s+/g, " ")
    .trim();

  return truncateWords(normalized, 4);
}

export function prepareJourneyDescriptionForDisplay(text: string): string {
  return truncateWords(normalizeDisplayText(text), 26);
}

export function prepareProductExplanationForDisplay(text: string): string {
  return truncateWords(normalizeDisplayText(text), 20);
}

export function prepareInterpretationForDisplay(text: string): string {
  return truncateWords(normalizeDisplayText(text), 18);
}

export function cleanPublicText(text: string | undefined): string {
  const normalized = normalizeDisplayText(text);

  if (!normalized) {
    return "";
  }

  if (PUBLIC_NOISE_PATTERNS.some((pattern) => pattern.test(normalized))) {
    return "";
  }

  if (/(?:\.\.\.|…)$/.test(normalized) || /['’]$/.test(normalized)) {
    return "";
  }

  if (/[;:,/\\-]$/.test(normalized)) {
    return "";
  }

  const cleaned = normalized
    .replace(/([.!?]){2,}/g, "$1")
    .replace(/\s+([.!?;,])/g, "$1")
    .replace(/\s{2,}/g, " ")
    .trim();

  if (!cleaned) {
    return "";
  }

  const lowered = cleaned
    .toLowerCase()
    .replace(/^[\s.,!?:;]+|[\s.,!?:;]+$/g, "")
    .replace(/\s+/g, " ");
  const emptyFillers = new Set([
    "this remains a central caution",
    "unspecified",
    "none",
    "no material evidence limitation was identified",
    "no material evidence limitation was identified for this answer",
    "no material uncertainty could be mapped from the available evidence",
    "no material uncertainty was identified",
    "uncertainty note: unspecified",
    "uncertainty note unspecified",
  ]);
  if (emptyFillers.has(lowered)) {
    return "";
  }

  if (PUBLIC_MALFORMED_PATTERNS.some((pattern) => pattern.test(cleaned))) {
    return "";
  }

  return cleaned;
}

export function cleanPublicList(
  values: string[],
  options?: {
    limit?: number;
    seen?: Set<string>;
  },
): string[] {
  const seen = options?.seen ?? new Set<string>();
  const limit = options?.limit ?? 3;
  const cleaned: string[] = [];

  for (const value of values) {
    const text = cleanPublicText(value);
    if (!text) {
      continue;
    }

    const key = normalizeComparableText(text);
    if (!key) {
      continue;
    }

    if ([...seen].some((existing) => isNearDuplicate(key, existing))) {
      continue;
    }

    seen.add(key);
    cleaned.push(text);

    if (cleaned.length >= limit) {
      break;
    }
  }

  return cleaned;
}

function stripKnownPrefixes(text: string, prefixes: RegExp[]) {
  return prefixes.reduce((value, pattern) => value.replace(pattern, ""), text).trim();
}

function normalizeDisplayText(text: string | undefined) {
  const safeText = text ?? "";
  return safeText
    .replace(/appearslinked/gi, "appears linked")
    .replace(/canlag/gi, "can lag")
    .replace(/\s+/g, " ")
    .trim();
}

function normalizeComparableText(text: string) {
  return cleanPublicText(text)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\b(?:a|an|and|are|as|at|be|but|by|for|from|in|into|is|it|its|of|on|or|that|the|their|this|to|was|were|with)\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function isNearDuplicate(candidate: string, existing: string) {
  if (!candidate || !existing) {
    return false;
  }

  if (candidate === existing) {
    return true;
  }

  const candidateTokens = new Set(candidate.split(" ").filter(Boolean));
  const existingTokens = new Set(existing.split(" ").filter(Boolean));

  if (candidateTokens.size === 0 || existingTokens.size === 0) {
    return false;
  }

  let shared = 0;
  for (const token of candidateTokens) {
    if (existingTokens.has(token)) {
      shared += 1;
    }
  }

  const smaller = Math.min(candidateTokens.size, existingTokens.size);
  return shared >= 3 && shared / smaller >= 0.75;
}

export function shouldRenderProgression(
  questionType: QuestionPresentationType,
  progression: ProgressionInsight | null | undefined,
) {
  if (!progression) {
    return false;
  }

  if (progression.turningPoints.length > 0) {
    return true;
  }

  return questionType === "progression" && Boolean(
    progression.headline ||
      progression.currentState ||
      progression.whatChanged ||
      progression.whyItChanged ||
      progression.latestEvidence.length ||
      progression.unresolvedItems.length,
  );
}

export function finalizeProgressionForDisplay(
  questionType: QuestionPresentationType,
  progression: ProgressionInsight | null | undefined,
): ProgressionInsight | null {
  if (!shouldRenderProgression(questionType, progression)) {
    return null;
  }

  return {
    headline: cleanPublicText(progression?.headline ?? ""),
    currentState: cleanPublicText(progression?.currentState ?? ""),
    whatChanged: cleanPublicText(progression?.whatChanged ?? ""),
    whyItChanged: cleanPublicText(progression?.whyItChanged ?? ""),
    convictionImpact: progression?.convictionImpact ?? "unclear",
    latestEvidence: cleanPublicList(progression?.latestEvidence ?? [], { limit: 4 }),
    unresolvedItems: cleanPublicList(progression?.unresolvedItems ?? [], { limit: 4 }),
    turningPoints: (progression?.turningPoints ?? [])
      .map((point) => ({
        period: cleanPublicText(point.period ?? ""),
        label: cleanPublicText(point.label ?? ""),
        description: cleanPublicText(point.description ?? ""),
        whyItMatters: cleanPublicText(point.whyItMatters ?? ""),
        impact: point.impact ?? "unclear",
      }))
      .filter((point) => point.label || point.description)
      .slice(0, 6),
  };
}

export function finalizeResearchAnswerForDisplay(answer: ResearchAnswer): ResearchAnswer {
  const uncertaintyDetail = cleanPublicText(answer.uncertaintyNote?.detail ?? "");
  const whatChanged = Array.isArray(answer.whatChanged)
    ? cleanPublicText(answer.whatChanged.join(" "))
    : cleanPublicText(answer.whatChanged ?? "");

  return {
    ...answer,
    questionTitle: cleanPublicText(answer.questionTitle ?? answer.question),
    question: cleanPublicText(answer.question),
    directAnswer: cleanPublicText(answer.directAnswer),
    conciseAnswer: cleanPublicText(answer.conciseAnswer ?? answer.directAnswer),
    explanation: cleanPublicText(answer.explanation),
    whyItMatters: cleanPublicText(answer.whyItMatters ?? answer.explanation) || undefined,
    supportingPoints: answer.supportingPoints
      .map((point) => ({
        title: cleanPublicText(point.title),
        detail: cleanPublicText(point.detail),
      }))
      .filter((point) => point.title || point.detail)
      .slice(0, 4),
    uncertaintyNote: {
      label: cleanPublicText(answer.uncertaintyNote?.label ?? "Uncertainty note") || "Uncertainty note",
      detail: uncertaintyDetail,
    },
    supportingEvidence: answer.supportingEvidence
      .map((item) => ({
        label: cleanPublicText(item.label),
        detail: cleanPublicText(item.detail),
      }))
      .filter((item) => item.detail)
      .slice(0, 3),
    evidenceSummary: answer.evidenceSummary
      ? answer.evidenceSummary
          .map((item) => ({
            label: cleanPublicText(item.label),
            detail: cleanPublicText(item.detail),
          }))
          .filter((item) => item.detail)
          .slice(0, 3)
      : answer.evidenceSummary,
    conclusion: cleanPublicText(answer.conclusion ?? ""),
    whatChanged,
    whyItChanged: cleanPublicText(answer.whyItChanged ?? ""),
    rawNumbers: cleanPublicList(answer.rawNumbers ?? [], { limit: 4 }),
    unresolved: cleanPublicList(answer.unresolved ?? [], { limit: 3 }),
    followUpQuestions: cleanPublicList(answer.followUpQuestions ?? [], { limit: 3 }),
    evidence: answer.evidence
      ? answer.evidence
          .map((item) => ({
            label: cleanPublicText(item.label),
            detail: cleanPublicText(item.detail),
            sourceKey: item.sourceKey,
            period: item.period,
          }))
          .filter((item) => item.detail)
      : answer.evidence,
  };
}

export function finalizeResearchAnswerCardForDisplay(
  answer: ResearchAnswerCard,
): ResearchAnswerCard {
  return {
    ...answer,
    title: cleanPublicText(answer.title),
    simpleAnswer: cleanPublicText(answer.simpleAnswer),
    whyItMatters: cleanPublicText(answer.whyItMatters ?? ""),
    keyPoints: cleanPublicList(answer.keyPoints ?? [], { limit: 4 }),
    detailedExplanation: cleanPublicText(answer.detailedExplanation),
    businessJourney: answer.businessJourney
      ? {
          ...answer.businessJourney,
          summary: cleanPublicText(answer.businessJourney.summary),
          currentDirection: cleanPublicText(answer.businessJourney.currentDirection),
          openQuestions: cleanPublicList(answer.businessJourney.openQuestions ?? [], { limit: 4 }),
          stages: (answer.businessJourney.stages ?? [])
            .map((stage) => ({
              ...stage,
              title: cleanPublicText(stage.title),
              simpleDescription: cleanPublicText(stage.simpleDescription),
              significance: cleanPublicText(stage.significance),
            }))
            .filter((stage) => stage.title || stage.simpleDescription),
        }
      : answer.businessJourney,
    customerRoles: answer.customerRoles
      ? {
          ...answer.customerRoles,
          payers: cleanPublicList(answer.customerRoles.payers ?? [], { limit: 4 }),
          integratorsOrPartners: cleanPublicList(answer.customerRoles.integratorsOrPartners ?? [], { limit: 4 }),
          endUsers: cleanPublicList(answer.customerRoles.endUsers ?? [], { limit: 4 }),
          internationalCustomers: cleanPublicList(answer.customerRoles.internationalCustomers ?? [], { limit: 4 }),
          concentrationNote: cleanPublicText(answer.customerRoles.concentrationNote),
        }
      : answer.customerRoles,
    revenueFlow: answer.revenueFlow
      ? {
          ...answer.revenueFlow,
          steps: (answer.revenueFlow.steps ?? [])
            .map((step) => ({
              ...step,
              label: cleanPublicText(step.label),
              explanation: cleanPublicText(step.explanation),
            }))
            .filter((step) => step.label || step.explanation),
          billingBasisNote: cleanPublicText(answer.revenueFlow.billingBasisNote ?? "") || undefined,
          revenueRecognitionNote: cleanPublicText(answer.revenueFlow.revenueRecognitionNote ?? "") || undefined,
          cashTimingNote: cleanPublicText(answer.revenueFlow.cashTimingNote ?? "") || undefined,
          workingCapitalNote: cleanPublicText(answer.revenueFlow.workingCapitalNote ?? "") || undefined,
          offeringExamples: cleanPublicList(answer.revenueFlow.offeringExamples ?? [], { limit: 4 }),
        }
      : answer.revenueFlow,
    structuredSections: answer.structuredSections
      ? answer.structuredSections
          .map((section) => ({
            title: cleanPublicText(section.title),
            points: cleanPublicList(section.points ?? [], { limit: 3 }),
          }))
          .filter((section) => section.title && section.points.length > 0)
      : answer.structuredSections,
    progression: finalizeProgressionForDisplay(answer.questionType, answer.progression ?? null),
    interpretation: answer.interpretation
      ? {
          ...answer.interpretation,
          conclusion: cleanPublicText(answer.interpretation.conclusion),
          whatChanged: cleanPublicList(answer.interpretation.whatChanged ?? [], { limit: 3 }),
          whyItMatters: cleanPublicText(answer.interpretation.whyItMatters),
          economicMechanism: cleanPublicText(answer.interpretation.economicMechanism),
          positiveEvidence: cleanPublicList(answer.interpretation.positiveEvidence ?? [], { limit: 3 }),
          negativeEvidence: cleanPublicList(answer.interpretation.negativeEvidence ?? [], { limit: 3 }),
          unresolved: cleanPublicList(answer.interpretation.unresolved ?? [], { limit: 3 }),
          whatToWatch: cleanPublicList(answer.interpretation.whatToWatch ?? [], { limit: 3 }),
          confidence: {
            ...answer.interpretation.confidence,
            basis: cleanPublicList(answer.interpretation.confidence.basis ?? [], { limit: 2 }),
            limitations: cleanPublicList(answer.interpretation.confidence.limitations ?? [], { limit: 2 }),
          },
        }
      : answer.interpretation,
    evidenceSummary: answer.evidenceSummary
      .map((item) => ({
        ...item,
        label: cleanPublicText(item.label),
        detail: cleanPublicText(item.detail),
      }))
      .filter((item) => item.detail),
    uncertaintyNote: {
      ...answer.uncertaintyNote,
      label: cleanPublicText(answer.uncertaintyNote.label) || "Uncertainty note",
      detail: cleanPublicText(answer.uncertaintyNote.detail),
    },
  };
}

function truncateWords(text: string, limit: number) {
  const words = text.split(/\s+/).filter(Boolean);

  if (words.length <= limit) {
    return text;
  }

  return `${words.slice(0, limit).join(" ")}…`;
}
