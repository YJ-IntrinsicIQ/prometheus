export type ProgressionImpact = "strengthened" | "weakened" | "unchanged" | "unclear";

export type TurningPoint = {
  period: string;
  label: string;
  description: string;
  whyItMatters: string;
  impact: ProgressionImpact;
};

export type ProgressionInsight = {
  headline: string;
  currentState: string;
  whatChanged: string;
  whyItChanged: string;
  convictionImpact: ProgressionImpact;
  latestEvidence: string[];
  unresolvedItems: string[];
  turningPoints: TurningPoint[];
};
