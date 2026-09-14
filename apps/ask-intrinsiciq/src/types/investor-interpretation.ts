import type { AskConfidenceLevel } from "@/src/lib/prometheus/ask-v2/answer-contracts";

export type ThesisImpact = "strengthens" | "weakens" | "mixed" | "neutral" | "unresolved";

// ENG-122 five-tier evidence classification; counts from backend, not recomputed here
export type OutcomeAttributionSummary = {
  directly_attributable?: number;
  strongly_supported?: number;
  associated_not_attributable?: number;
  no_outcome_evidence?: number;
  negative_outcome?: number;
};

export type InvestorInterpretation = {
  conclusion: string;
  whatChanged: string[];
  whyItMatters: string;
  economicMechanism: string;
  thesisImpact: ThesisImpact;
  positiveEvidence: string[];
  negativeEvidence: string[];
  unresolved: string[];
  whatToWatch: string[];
  confidence: {
    level: AskConfidenceLevel;
    basis: string[];
    limitations: string[];
  };
  outcomeAttributionSummary?: OutcomeAttributionSummary | null;
};
