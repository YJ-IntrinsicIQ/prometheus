import type { AskIntentId, AskPlan, CanonicalSourceKey } from "./answer-contracts";

type IntentRule = {
  primaryIntent: AskIntentId;
  secondaryIntents: AskIntentId[];
  canonicalSourceKeys: CanonicalSourceKey[];
  requiresProgression?: boolean;
  requiresFinancialValues?: boolean;
  requiresInvestorLens?: boolean;
  requiresRawEvidence?: boolean;
  requiresRawDocumentFallback?: boolean;
  evidenceBudget?: number;
  limitations?: string[];
};

const QUESTION_ID_RULES: Record<string, IntentRule> = {
  "what-does-company-do": {
    primaryIntent: "business_understanding",
    secondaryIntents: ["cross_domain"],
    canonicalSourceKeys: ["pcim"],
    evidenceBudget: 5,
  },
  "who-are-the-customers": {
    primaryIntent: "business_understanding",
    secondaryIntents: ["cross_domain"],
    canonicalSourceKeys: ["pcim"],
    evidenceBudget: 5,
  },
  "how-does-it-make-money": {
    primaryIntent: "business_understanding",
    secondaryIntents: ["financial_performance", "cross_domain"],
    canonicalSourceKeys: ["pcim", "financialTruthPack", "ownerEarningsBridge"],
    requiresFinancialValues: true,
    evidenceBudget: 6,
  },
  "what-makes-the-offering-important": {
    primaryIntent: "business_understanding",
    secondaryIntents: ["cross_domain"],
    canonicalSourceKeys: ["pcim", "managementQualitySummary"],
    evidenceBudget: 5,
  },
  "where-is-evidence-thin": {
    primaryIntent: "diligence",
    secondaryIntents: ["unresolved_questions"],
    canonicalSourceKeys: ["committeeSynthesis", "financialTruthPack"],
    evidenceBudget: 5,
  },
  "are-profits-converting-into-cash": {
    primaryIntent: "financial_performance",
    secondaryIntents: ["owner_earnings", "working_capital", "financial_progression"],
    canonicalSourceKeys: ["financialTruthPack", "ownerEarningsBridge", "workingCapitalQuality", "perShareCompounding"],
    requiresProgression: true,
    requiresFinancialValues: true,
    evidenceBudget: 7,
  },
  "what-is-owner-earnings": {
    primaryIntent: "owner_earnings",
    secondaryIntents: ["financial_performance", "financial_progression"],
    canonicalSourceKeys: ["financialTruthPack", "ownerEarningsBridge", "workingCapitalQuality"],
    requiresFinancialValues: true,
    requiresProgression: true,
    evidenceBudget: 6,
  },
  "is-working-capital-a-concern": {
    primaryIntent: "working_capital",
    secondaryIntents: ["financial_progression", "financial_performance"],
    canonicalSourceKeys: ["workingCapitalQuality", "financialTruthPack"],
    requiresProgression: true,
    requiresFinancialValues: true,
    evidenceBudget: 6,
  },
  "are-per-share-economics-improving": {
    primaryIntent: "per_share_compounding",
    secondaryIntents: ["financial_progression", "owner_earnings"],
    canonicalSourceKeys: ["perShareCompounding", "financialTruthPack", "ownerEarningsBridge"],
    requiresProgression: true,
    requiresFinancialValues: true,
    evidenceBudget: 6,
  },
  "which-financial-assumption-matters-most": {
    primaryIntent: "cross_domain",
    secondaryIntents: ["owner_earnings", "financial_performance"],
    canonicalSourceKeys: ["financialTruthPack", "ownerEarningsBridge", "committeeSynthesis"],
    requiresFinancialValues: true,
    evidenceBudget: 6,
  },
  "what-has-management-promised": {
    primaryIntent: "management_commitments",
    secondaryIntents: ["management_commentary", "projects"],
    canonicalSourceKeys: ["managementCommitments", "commentaryAssessments", "commentaryTimelines", "projectAssessments"],
    requiresProgression: true,
    evidenceBudget: 7,
  },
  "did-past-claims-come-true": {
    primaryIntent: "management_commitments",
    secondaryIntents: ["projects", "capacity", "management_quality"],
    canonicalSourceKeys: ["managementCommitments", "projectAssessments", "capacityAssessments", "managementQualitySummary"],
    requiresProgression: true,
    evidenceBudget: 8,
  },
  "what-projects-are-underway": {
    primaryIntent: "projects",
    secondaryIntents: ["capacity", "management_commitments"],
    canonicalSourceKeys: ["projectAssessments", "projectTimelines", "managementCommitments", "capacityAssessments"],
    requiresProgression: true,
    evidenceBudget: 7,
  },
  "how-is-capacity-changing": {
    primaryIntent: "capacity",
    secondaryIntents: ["projects", "management_commitments"],
    canonicalSourceKeys: ["capacityAssessments", "capacityTimelines", "projectAssessments", "managementCommitments"],
    requiresProgression: true,
    evidenceBudget: 7,
  },
  "what-is-management-commentary-saying": {
    primaryIntent: "management_commentary",
    secondaryIntents: ["management_commitments", "management_quality"],
    canonicalSourceKeys: ["commentaryAssessments", "commentaryTimelines", "managementQualitySummary"],
    requiresProgression: true,
    evidenceBudget: 7,
  },
  "how-is-capital-allocated": {
    primaryIntent: "capital_allocation",
    secondaryIntents: ["management_quality", "per_share_compounding", "owner_earnings"],
    canonicalSourceKeys: ["capitalAllocationRoi", "capitalAllocationOutcomes", "capitalAllocationTimelines", "managementQualitySummary", "financialTruthPack"],
    requiresProgression: true,
    requiresFinancialValues: true,
    evidenceBudget: 8,
  },
  "what-incentives-matter": {
    primaryIntent: "management_quality",
    secondaryIntents: ["capital_allocation", "management_commitments"],
    canonicalSourceKeys: ["managementQualitySummary", "managementQualityDimensions", "managementCommitments"],
    requiresProgression: true,
    evidenceBudget: 6,
  },
  "what-should-i-ask-ir": {
    primaryIntent: "diligence",
    secondaryIntents: ["unresolved_questions", "committee_view"],
    canonicalSourceKeys: ["committeeSynthesis", "committeeBriefQa"],
    evidenceBudget: 6,
  },
  "what-would-graham-worry-about": {
    primaryIntent: "investor_lens",
    secondaryIntents: ["risk", "financial_performance"],
    canonicalSourceKeys: ["grahamAnalysis", "committeeSynthesis", "financialTruthPack", "workingCapitalQuality"],
    requiresInvestorLens: true,
    requiresFinancialValues: true,
    evidenceBudget: 7,
  },
  "what-would-buffett-focus-on": {
    primaryIntent: "investor_lens",
    secondaryIntents: ["management_quality", "capital_allocation", "financial_performance"],
    canonicalSourceKeys: ["buffettAnalysis", "managementQualitySummary", "capitalAllocationRoi", "committeeSynthesis"],
    requiresInvestorLens: true,
    evidenceBudget: 7,
  },
  "where-would-fisher-be-curious": {
    primaryIntent: "investor_lens",
    secondaryIntents: ["projects", "capacity", "management_commitments"],
    canonicalSourceKeys: ["fisherAnalysis", "projectAssessments", "capacityAssessments", "managementCommitments"],
    requiresInvestorLens: true,
    requiresProgression: true,
    evidenceBudget: 7,
  },
  "what-would-munger-avoid": {
    primaryIntent: "investor_lens",
    secondaryIntents: ["management_quality", "capital_allocation", "risk"],
    canonicalSourceKeys: ["mungerAnalysis", "managementQualitySummary", "committeeSynthesis", "capitalAllocationRoi"],
    requiresInvestorLens: true,
    evidenceBudget: 7,
  },
  "how-would-lynch-explain-it": {
    primaryIntent: "investor_lens",
    secondaryIntents: ["business_understanding", "financial_performance"],
    canonicalSourceKeys: ["lynchAnalysis", "pcim", "financialTruthPack"],
    requiresInvestorLens: true,
    requiresFinancialValues: true,
    evidenceBudget: 6,
  },
  "what-can-break-the-thesis": {
    primaryIntent: "risk",
    secondaryIntents: ["committee_view", "unresolved_questions"],
    canonicalSourceKeys: ["riskAssessments", "riskTimelines", "committeeSynthesis"],
    requiresProgression: true,
    evidenceBudget: 7,
  },
  "which-disclosure-is-missing": {
    primaryIntent: "diligence",
    secondaryIntents: ["unresolved_questions", "raw_document_fact"],
    canonicalSourceKeys: ["committeeSynthesis", "committeeBriefQa", "financialTruthPack"],
    requiresRawEvidence: true,
    evidenceBudget: 6,
  },
  "what-evidence-would-change-the-view": {
    primaryIntent: "thesis_change",
    secondaryIntents: ["diligence", "committee_view"],
    canonicalSourceKeys: ["committeeSynthesis", "committeeBriefQa", "managementQualitySummary"],
    evidenceBudget: 6,
  },
  "what-needs-management-clarification": {
    primaryIntent: "diligence",
    secondaryIntents: ["management_commitments", "committee_view"],
    canonicalSourceKeys: ["committeeSynthesis", "managementCommitments", "managementQualitySummary"],
    evidenceBudget: 6,
  },
  "what-remains-unresolved": {
    primaryIntent: "unresolved_questions",
    secondaryIntents: ["committee_view", "diligence"],
    canonicalSourceKeys: ["committeeSynthesis", "committeeBriefQa", "managementQualitySummary"],
    requiresProgression: true,
    evidenceBudget: 6,
  },
  "what-are-key-risks": {
    primaryIntent: "risk",
    secondaryIntents: ["committee_view"],
    canonicalSourceKeys: ["riskAssessments", "riskTimelines", "committeeSynthesis"],
    requiresProgression: true,
    evidenceBudget: 7,
  },
};

export function buildAskPlan(question: string, questionId?: string): AskPlan {
  const normalizedQuestion = normalizeQuestionText(question);
  const rule = (questionId && QUESTION_ID_RULES[questionId.trim()]) || inferIntentFromText(normalizedQuestion);
  return {
    question: normalizedQuestion,
    questionId: questionId?.trim() || undefined,
    primaryIntent: rule.primaryIntent,
    secondaryIntents: rule.secondaryIntents,
    canonicalSourceKeys: rule.canonicalSourceKeys,
    requiresProgression: Boolean(rule.requiresProgression),
    requiresFinancialValues: Boolean(rule.requiresFinancialValues),
    requiresInvestorLens: Boolean(rule.requiresInvestorLens),
    requiresRawEvidence: Boolean(rule.requiresRawEvidence),
    requiresRawDocumentFallback: Boolean(rule.requiresRawDocumentFallback),
    evidenceBudget: rule.evidenceBudget ?? 6,
    limitations: rule.limitations ? [...rule.limitations] : [],
  };
}

export function inferIntentFromText(question: string): IntentRule {
  const lower = question.toLowerCase();

  if (/(delivered|promise|promis|commitment|follow-through|follow through)/.test(lower)) {
    return {
      primaryIntent: "management_commitments",
      secondaryIntents: ["projects", "capacity", "management_quality"],
      canonicalSourceKeys: ["managementCommitments", "projectAssessments", "capacityAssessments", "managementQualitySummary"],
      requiresProgression: true,
      evidenceBudget: 7,
    };
  }

  if (/(capital allocation|allocate capital|capex|return on capital|productive capital)/.test(lower)) {
    return {
      primaryIntent: "capital_allocation",
      secondaryIntents: ["management_quality", "financial_performance", "per_share_compounding"],
      canonicalSourceKeys: ["capitalAllocationRoi", "capitalAllocationOutcomes", "managementQualitySummary", "financialTruthPack"],
      requiresProgression: true,
      requiresFinancialValues: true,
      evidenceBudget: 8,
    };
  }

  if (/(capacity|commission|utilization|plant|factory|facility|new plant|new capacity)/.test(lower)) {
    return {
      primaryIntent: "capacity",
      secondaryIntents: ["projects", "management_commitments", "capital_allocation"],
      canonicalSourceKeys: ["capacityAssessments", "capacityTimelines", "projectAssessments", "managementCommitments"],
      requiresProgression: true,
      evidenceBudget: 7,
    };
  }

  if (/(project|programme|program|expansion|initiative)/.test(lower)) {
    return {
      primaryIntent: "projects",
      secondaryIntents: ["capacity", "management_commitments", "capital_allocation"],
      canonicalSourceKeys: ["projectAssessments", "projectTimelines", "capacityAssessments", "managementCommitments"],
      requiresProgression: true,
      evidenceBudget: 7,
    };
  }

  if (/(risk|risk[s]?|concern|worry|uncertain|threat)/.test(lower)) {
    return {
      primaryIntent: "risk",
      secondaryIntents: ["committee_view", "management_quality"],
      canonicalSourceKeys: ["riskAssessments", "riskTimelines", "committeeSynthesis", "managementQualitySummary"],
      requiresProgression: true,
      evidenceBudget: 7,
    };
  }

  if (/(commentary|management said|management commentary|what changed in management language|what changed in commentary)/.test(lower)) {
    return {
      primaryIntent: "management_commentary",
      secondaryIntents: ["management_commitments", "management_quality"],
      canonicalSourceKeys: ["commentaryAssessments", "commentaryTimelines", "managementQualitySummary"],
      requiresProgression: true,
      evidenceBudget: 7,
    };
  }

  if (/(buffett|graham|fisher|munger|lynch)/.test(lower)) {
    return {
      primaryIntent: "investor_lens",
      secondaryIntents: ["committee_view", "management_quality", "capital_allocation"],
      canonicalSourceKeys: ["buffettAnalysis", "grahamAnalysis", "fisherAnalysis", "mungerAnalysis", "lynchAnalysis", "committeeSynthesis"],
      requiresInvestorLens: true,
      evidenceBudget: 7,
    };
  }

  if (/(committee|analyst disagreement|disagree|view|thesis|strengthened|weakened|unresolved|what changed|why did it change)/.test(lower)) {
    return {
      primaryIntent: /disagree/.test(lower) ? "disagreement" : /unresolved/.test(lower) ? "unresolved_questions" : "committee_view",
      secondaryIntents: ["thesis_change", "diligence"],
      canonicalSourceKeys: ["committeeSynthesis", "committeeBriefQa", "managementQualitySummary"],
      requiresProgression: true,
      evidenceBudget: 7,
    };
  }

  if (/(revenue|profit|pat|cash|owner earnings|working capital|per share|per-share|eps|financial)/.test(lower)) {
    return {
      primaryIntent: "financial_performance",
      secondaryIntents: ["financial_progression", "owner_earnings", "working_capital", "per_share_compounding"],
      canonicalSourceKeys: ["financialTruthPack", "ownerEarningsBridge", "workingCapitalQuality", "perShareCompounding"],
      requiresProgression: true,
      requiresFinancialValues: true,
      evidenceBudget: 7,
    };
  }

  if (/(why|what should i investigate|what should i ask|next question|diligence|investigate next|follow up)/.test(lower)) {
    return {
      primaryIntent: "diligence",
      secondaryIntents: ["unresolved_questions", "committee_view"],
      canonicalSourceKeys: ["committeeSynthesis", "committeeBriefQa", "managementQualitySummary"],
      requiresProgression: true,
      evidenceBudget: 6,
    };
  }

  if (/(raw|exact|what did management say|what was revenue|what did they disclose)/.test(lower)) {
    return {
      primaryIntent: "raw_document_fact",
      secondaryIntents: ["management_commentary", "financial_performance"],
      canonicalSourceKeys: ["financialTruthPack", "managementCommitments", "commentaryAssessments", "rawDiscoveryBundles"],
      requiresRawEvidence: true,
      requiresRawDocumentFallback: true,
      evidenceBudget: 5,
    };
  }

  if (/(how has|changed over time|improved|worsened|evolved|trend|progression|journey|delivery|before|after|now)/.test(lower)) {
    return {
      primaryIntent: "thesis_change",
      secondaryIntents: ["financial_progression", "management_quality", "committee_view"],
      canonicalSourceKeys: ["committeeSynthesis", "managementQualitySummary", "financialTruthPack", "projectAssessments", "capacityAssessments"],
      requiresProgression: true,
      evidenceBudget: 8,
    };
  }

  if (/(better business|cross domain|overall business|actually improved|become a better business)/.test(lower)) {
    return {
      primaryIntent: "cross_domain",
      secondaryIntents: ["financial_progression", "management_quality", "capital_allocation", "projects", "capacity", "risk", "committee_view"],
      canonicalSourceKeys: ["financialTruthPack", "managementQualitySummary", "committeeSynthesis", "projectAssessments", "capacityAssessments", "riskAssessments"],
      requiresProgression: true,
      requiresFinancialValues: true,
      evidenceBudget: 10,
    };
  }

  return {
    primaryIntent: "unknown",
    secondaryIntents: [],
    canonicalSourceKeys: ["committeeSynthesis", "managementQualitySummary"],
    requiresProgression: false,
    evidenceBudget: 4,
  };
}

export function normalizeQuestionText(question: string) {
  return question.replace(/\s+/g, " ").trim();
}
