export type AskIntentId =
  | "business_understanding"
  | "financial_performance"
  | "financial_progression"
  | "owner_earnings"
  | "working_capital"
  | "per_share_compounding"
  | "management_commitments"
  | "management_quality"
  | "projects"
  | "capacity"
  | "risk"
  | "management_commentary"
  | "capital_allocation"
  | "investor_lens"
  | "committee_view"
  | "disagreement"
  | "thesis_change"
  | "unresolved_questions"
  | "diligence"
  | "raw_document_fact"
  | "cross_domain"
  | "unknown";

export type CanonicalSourceKey =
  | "pcim"
  | "companyModel"
  | "managementProgression"
  | "financialTruthPack"
  | "ownerEarningsBridge"
  | "workingCapitalQuality"
  | "capitalAllocationRoi"
  | "perShareCompounding"
  | "managementCommitments"
  | "projectAssessments"
  | "projectTimelines"
  | "capacityAssessments"
  | "capacityTimelines"
  | "riskAssessments"
  | "riskTimelines"
  | "commentaryAssessments"
  | "commentaryTimelines"
  | "commentaryThemes"
  | "managementQualitySummary"
  | "managementQualityDimensions"
  | "capitalAllocationOutcomes"
  | "capitalAllocationTimelines"
  | "buffettAnalysis"
  | "grahamAnalysis"
  | "fisherAnalysis"
  | "mungerAnalysis"
  | "lynchAnalysis"
  | "committeeSynthesis"
  | "committeeBriefQa"
  | "panelRunSummary"
  | "rawDiscoveryBundles";

export type AskConfidenceLevel = "high" | "medium" | "low" | "insufficient";

export type AskConvictionImpact = "strengthened" | "weakened" | "unchanged" | "unclear";

export type AskEvidenceItem = {
  label: string;
  detail: string;
  sourceKey: CanonicalSourceKey | "raw_document_fallback";
  period?: string;
};

export type AskSourceReference = {
  sourceKey: CanonicalSourceKey | "raw_document_fallback";
  label: string;
  period?: string;
  reference?: string;
};

export type AskPlan = {
  question: string;
  questionId?: string;
  primaryIntent: AskIntentId;
  secondaryIntents: AskIntentId[];
  canonicalSourceKeys: CanonicalSourceKey[];
  requiresProgression: boolean;
  requiresFinancialValues: boolean;
  requiresInvestorLens: boolean;
  requiresRawEvidence: boolean;
  requiresRawDocumentFallback: boolean;
  evidenceBudget: number;
  limitations: string[];
};

export type AskContextV2 = {
  plan: AskPlan;
  canonicalSourcesUsed: CanonicalSourceKey[];
  evidence: AskEvidenceItem[];
  progression: string[];
  rawNumbers: string[];
  unresolved: string[];
  sources: AskSourceReference[];
  confidence: AskConfidenceLevel;
  rawFallbackUsed: boolean;
  contextSize: number;
  limitations: string[];
};

export type AskDiagnostics = {
  detectedIntent: AskIntentId;
  canonicalSourcesUsed: CanonicalSourceKey[];
  rawFallbackUsed: boolean;
  evidenceCount: number;
  progressionUsed: boolean;
  contextSize: number;
  confidence: AskConfidenceLevel;
  validationStatus: "pass" | "warning" | "fail";
};
