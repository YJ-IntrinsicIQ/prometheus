import path from "node:path";

const VALID_SEGMENT_PATTERN = /^[a-z0-9-]+$/;

export type AskIntrinsicIqPaths = {
  repoRoot: string;
  companyRoot: string;
  outputRoot: string;
  companyResearchView: string;
  businessJourney: string;
  productsServices: string;
  answerCards: string;
  financialVisualSummaries: string;
  uncertaintyMap: string;
  manifest: string;
  validationReport: string;
};

export function getRepoRoot() {
  return process.env.ASK_INTRINSICIQ_REPO_ROOT
    ? path.resolve(process.env.ASK_INTRINSICIQ_REPO_ROOT)
    : path.resolve(process.cwd(), "..", "..");
}

export function isValidRouteSegment(value: string) {
  return VALID_SEGMENT_PATTERN.test(value);
}

export function getAskIntrinsicIqPaths(
  companySlug: string,
  repoRoot = getRepoRoot(),
): AskIntrinsicIqPaths | null {
  if (!isValidRouteSegment(companySlug)) {
    return null;
  }

  const companyRoot = path.join(repoRoot, "companies", companySlug);
  const outputRoot = path.join(
    companyRoot,
    "company_memory",
    "ask_intrinsiciq",
  );

  return {
    repoRoot,
    companyRoot,
    outputRoot,
    companyResearchView: path.join(outputRoot, "company_research_view.json"),
    businessJourney: path.join(outputRoot, "business_journey.json"),
    productsServices: path.join(outputRoot, "products_services.json"),
    answerCards: path.join(outputRoot, "answer_cards.json"),
    financialVisualSummaries: path.join(
      outputRoot,
      "financial_visual_summaries.json",
    ),
    uncertaintyMap: path.join(outputRoot, "uncertainty_map.json"),
    manifest: path.join(outputRoot, "ask_intrinsiciq_manifest.json"),
    validationReport: path.join(
      outputRoot,
      "ask_intrinsiciq_validation_report.json",
    ),
  };
}
