import type { AskConfidenceLevel } from "@/src/lib/prometheus/ask-v2/answer-contracts";

export type ThesisImpact = "strengthens" | "weakens" | "mixed" | "neutral" | "unresolved";

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
};
