import path from "node:path";

export type PrometheusAdapterPaths = {
  repoRoot: string;
  companyMemoryRoot: string;
  pcim: string;
  financialTruthPack: string;
  ownerEarningsBridge: string;
  workingCapitalQuality: string;
  capitalAllocationRoi: string;
  perShareCompounding: string;
  managementCommitments: string;
  projectAssessments: string;
  projectTimelines: string;
  capacityAssessments: string;
  capacityTimelines: string;
  riskAssessments: string;
  riskTimelines: string;
  riskEvolution: string;
  commentaryAssessments: string;
  commentaryTimelines: string;
  commentaryThemes: string;
  managementQualitySummary: string;
  managementQualityDimensions: string;
  capitalAllocationOutcomes: string;
  capitalAllocationTimelines: string;
  promiseTracker: string;
  companyRawYearsDir: string;
  investorPanelDir: string;
  buffettAnalysis: string;
  grahamAnalysis: string;
  fisherAnalysis: string;
  mungerAnalysis: string;
  lynchAnalysis: string;
  committeeSynthesis: string;
  committeeBriefQa: string;
  panelRunSummary: string;
};

export function getRepoRoot() {
  return process.env.ASK_INTRINSICIQ_REPO_ROOT
    ? path.resolve(process.env.ASK_INTRINSICIQ_REPO_ROOT)
    : path.resolve(process.cwd(), "..", "..");
}

export function getPrometheusPaths(
  companySlug: string,
  repoRoot = getRepoRoot(),
): PrometheusAdapterPaths {
  const companyMemoryRoot = path.join(
    repoRoot,
    "companies",
    companySlug,
    "company_memory",
  );
  const financialRoot = path.join(companyMemoryRoot, "financials");
  const investorFinancialRoot = path.join(
    financialRoot,
    "investor_financial_modules",
  );
  const managementCommitmentsRoot = path.join(companyMemoryRoot, "management_commitments");
  const projectsRoot = path.join(companyMemoryRoot, "projects");
  const capacityRoot = path.join(companyMemoryRoot, "capacity");
  const risksRoot = path.join(companyMemoryRoot, "risks");
  const commentaryRoot = path.join(companyMemoryRoot, "management_commentary");
  const managementQualityRoot = path.join(companyMemoryRoot, "management_quality");
  const capitalAllocationOutcomesRoot = path.join(companyMemoryRoot, "capital_allocation_outcomes");
  const investorPanelDir = path.join(companyMemoryRoot, "investor_panel");

  return {
    repoRoot,
    companyMemoryRoot,
    pcim: path.join(companyMemoryRoot, "pcim_v1.json"),
    financialTruthPack: path.join(financialRoot, "financial_truth_pack.json"),
    ownerEarningsBridge: path.join(
      investorFinancialRoot,
      "owner_earnings_bridge.json",
    ),
    workingCapitalQuality: path.join(
      investorFinancialRoot,
      "working_capital_quality_drilldown.json",
    ),
    capitalAllocationRoi: path.join(
      investorFinancialRoot,
      "capital_allocation_roi_ledger.json",
    ),
    perShareCompounding: path.join(
      investorFinancialRoot,
      "per_share_compounding_analysis.json",
    ),
    managementCommitments: path.join(managementCommitmentsRoot, "management_commitments.json"),
    projectAssessments: path.join(projectsRoot, "project_assessments.json"),
    projectTimelines: path.join(projectsRoot, "project_timelines.json"),
    capacityAssessments: path.join(capacityRoot, "capacity_assessments.json"),
    capacityTimelines: path.join(capacityRoot, "capacity_timelines.json"),
    riskAssessments: path.join(risksRoot, "risk_assessments.json"),
    riskTimelines: path.join(risksRoot, "risk_timelines.json"),
    riskEvolution: path.join(companyMemoryRoot, "multi_year", "risk_evolution.json"),
    commentaryAssessments: path.join(commentaryRoot, "commentary_assessments.json"),
    commentaryTimelines: path.join(commentaryRoot, "commentary_timelines.json"),
    commentaryThemes: path.join(commentaryRoot, "commentary_themes.json"),
    managementQualitySummary: path.join(managementQualityRoot, "management_quality_summary.json"),
    managementQualityDimensions: path.join(managementQualityRoot, "management_quality_dimensions.json"),
    capitalAllocationOutcomes: path.join(capitalAllocationOutcomesRoot, "capital_allocation_outcomes.json"),
    capitalAllocationTimelines: path.join(companyMemoryRoot, "capital_allocation_timeline.json"),
    promiseTracker: path.join(companyMemoryRoot, "multi_year", "promise_tracker.json"),
    companyRawYearsDir: companyMemoryRoot,
    investorPanelDir,
    buffettAnalysis: path.join(investorPanelDir, "buffett_analysis.json"),
    grahamAnalysis: path.join(investorPanelDir, "graham_analysis.json"),
    fisherAnalysis: path.join(investorPanelDir, "fisher_analysis.json"),
    mungerAnalysis: path.join(investorPanelDir, "munger_analysis.json"),
    lynchAnalysis: path.join(investorPanelDir, "lynch_analysis.json"),
    committeeSynthesis: path.join(
      investorPanelDir,
      "committee_synthesis.json",
    ),
    committeeBriefQa: path.join(investorPanelDir, "committee_brief_qa.json"),
    panelRunSummary: path.join(investorPanelDir, "panel_run_summary.json"),
  };
}
