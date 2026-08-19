import {
  getCompanyQuestionParams,
  getCompanyResearch as getDemoCompanyResearch,
  getCompanySlugs as getDemoCompanySlugs,
} from "@/src/data/demo-research";
import {
  buildCompanyResearchView,
  buildResearchAnswer,
  type RawSources,
} from "@/src/lib/prometheus/answer-builders";
import { getPrometheusPaths } from "@/src/lib/prometheus/paths";
import { readJsonIfExists } from "@/src/lib/prometheus/read-json";
import { buildDevelopmentNote, type SourceStatus } from "@/src/lib/prometheus/source-status";
import { readdir } from "node:fs/promises";
import path from "node:path";

export async function getCompanyResearchView(companySlug: string) {
  const demo = getDemoCompanyResearch(companySlug);

  if (!demo) {
    return null;
  }

  const loaded = await loadPrometheusSources(companySlug);
  return buildCompanyResearchView(companySlug, buildDevelopmentNote(loaded.status));
}

export async function getResearchAnswer(companySlug: string, questionId: string) {
  const demo = getDemoCompanyResearch(companySlug);

  if (!demo) {
    return null;
  }

  const loaded = await loadPrometheusSources(companySlug);
  return buildResearchAnswer(
    companySlug,
    questionId,
    loaded.sources,
    buildDevelopmentNote(loaded.status),
  );
}

export function getCompanySlugs() {
  return getDemoCompanySlugs();
}

export function getResearchQuestionParams() {
  return getCompanyQuestionParams();
}

export async function loadPrometheusSources(companySlug: string, repoRoot?: string) {
  const paths = getPrometheusPaths(companySlug, repoRoot);
  const status: SourceStatus = { available: [], missing: [] };

  async function load<T>(label: string, filePath: string) {
    const data = await readJsonIfExists<T>(filePath);
    if (data) {
      status.available.push(label);
    } else {
      status.missing.push(label);
    }
    return data;
  }

  const sources: RawSources = {
    pcim: await load<Record<string, unknown>>(
      "business intelligence summary",
      paths.pcim,
    ),
    companyModel: await load<Record<string, unknown>>(
      "company model",
      paths.companyModel,
    ),
    managementProgression: await load<Record<string, unknown>>(
      "management progression",
      paths.managementProgression,
    ),
    truthPack: await load<Record<string, unknown>>(
      "financial truth output",
      paths.financialTruthPack,
    ),
    ownerEarningsBridge: await load<Record<string, unknown>>(
      "owner earnings summary",
      paths.ownerEarningsBridge,
    ),
    workingCapitalQuality: await load<Record<string, unknown>>(
      "working capital quality summary",
      paths.workingCapitalQuality,
    ),
    capitalAllocationRoi: await load<Record<string, unknown>>(
      "capital allocation summary",
      paths.capitalAllocationRoi,
    ),
    perShareCompounding: await load<Record<string, unknown>>(
      "per-share compounding summary",
      paths.perShareCompounding,
    ),
    managementCommitments: await load<Record<string, unknown>>(
      "management commitments",
      paths.managementCommitments,
    ),
    projectAssessments: await load<Record<string, unknown>>(
      "project assessments",
      paths.projectAssessments,
    ),
    projectTimelines: await load<Record<string, unknown>>(
      "project timelines",
      paths.projectTimelines,
    ),
    capacityAssessments: await load<Record<string, unknown>>(
      "capacity assessments",
      paths.capacityAssessments,
    ),
    capacityTimelines: await load<Record<string, unknown>>(
      "capacity timelines",
      paths.capacityTimelines,
    ),
    riskAssessments: await load<Record<string, unknown>>(
      "risk assessments",
      paths.riskAssessments,
    ),
    riskTimelines: await load<Record<string, unknown>>(
      "risk timelines",
      paths.riskTimelines,
    ),
    riskEvolution: await load<Record<string, unknown>>(
      "risk evolution",
      paths.riskEvolution,
    ),
    commentaryAssessments: await load<Record<string, unknown>>(
      "commentary assessments",
      paths.commentaryAssessments,
    ),
    commentaryTimelines: await load<Record<string, unknown>>(
      "commentary timelines",
      paths.commentaryTimelines,
    ),
    commentaryThemes: await load<Record<string, unknown>>(
      "commentary themes",
      paths.commentaryThemes,
    ),
    managementQualitySummary: await load<Record<string, unknown>>(
      "management quality summary",
      paths.managementQualitySummary,
    ),
    managementQualityDimensions: await load<Record<string, unknown>>(
      "management quality dimensions",
      paths.managementQualityDimensions,
    ),
    capitalAllocationOutcomes: await load<Record<string, unknown>>(
      "capital allocation outcomes",
      paths.capitalAllocationOutcomes,
    ),
    capitalAllocationTimelines: await load<Record<string, unknown>>(
      "capital allocation timeline",
      paths.capitalAllocationTimelines,
    ),
    promiseTracker: await load<Record<string, unknown>>(
      "promise tracker",
      paths.promiseTracker,
    ),
    buffettAnalysis: await load<Record<string, unknown>>(
      "Buffett investor view",
      paths.buffettAnalysis,
    ),
    grahamAnalysis: await load<Record<string, unknown>>(
      "Graham investor view",
      paths.grahamAnalysis,
    ),
    fisherAnalysis: await load<Record<string, unknown>>(
      "Fisher investor view",
      paths.fisherAnalysis,
    ),
    mungerAnalysis: await load<Record<string, unknown>>(
      "Munger investor view",
      paths.mungerAnalysis,
    ),
    lynchAnalysis: await load<Record<string, unknown>>(
      "Lynch investor view",
      paths.lynchAnalysis,
    ),
    committeeSynthesis: await load<Record<string, unknown>>(
      "committee synthesis",
      paths.committeeSynthesis,
    ),
    committeeBriefQa: await load<Record<string, unknown>>(
      "committee brief summary",
      paths.committeeBriefQa,
    ),
    panelRunSummary: await load<Record<string, unknown>>(
      "panel summary",
      paths.panelRunSummary,
    ),
    rawDiscoveryBundles: await loadRawDiscoveryBundles(paths.companyRawYearsDir),
  };

  return { sources, status };
}

async function loadRawDiscoveryBundles(companyMemoryRoot: string) {
  const bundles: Array<Record<string, unknown>> = [];
  let entries;
  try {
    entries = await readdir(companyMemoryRoot, { withFileTypes: true });
  } catch {
    return bundles;
  }
  const yearDirs = entries.filter((entry) => entry.isDirectory() && /^fy\d+/i.test(entry.name));
  for (const entry of yearDirs) {
    const yearRoot = path.join(companyMemoryRoot, entry.name, "raw");
    const bundle = await loadRawDiscoveryBundle(yearRoot, entry.name);
    if (bundle) {
      bundles.push(bundle);
    }
  }
  return bundles;
}

async function loadRawDiscoveryBundle(rawDir: string, period: string) {
  const promiseDiscoveries = await readJsonIfExists(path.join(rawDir, "promise_discovery_results.json"));
  const projectDiscoveries = await readJsonIfExists(path.join(rawDir, "project_discovery_results.json"));
  const capacityDiscoveries = await readJsonIfExists(path.join(rawDir, "capacity_discovery_results.json"));
  const riskDiscoveries = await readJsonIfExists(path.join(rawDir, "risk_discovery_results.json"));
  const commentaryDiscoveries = await readJsonIfExists(path.join(rawDir, "commentary_discovery_results.json"));
  const capitalAllocationDiscoveries = await readJsonIfExists(path.join(rawDir, "capital_allocation_discovery_results.json"));
  const initiativeDiscoveries = await readJsonIfExists(path.join(rawDir, "initiative_discovery_results.json"));
  if (
    !promiseDiscoveries &&
    !projectDiscoveries &&
    !capacityDiscoveries &&
    !riskDiscoveries &&
    !commentaryDiscoveries &&
    !capitalAllocationDiscoveries &&
    !initiativeDiscoveries
  ) {
    return null;
  }
  return {
    period,
    promiseDiscoveries,
    projectDiscoveries,
    capacityDiscoveries,
    riskDiscoveries,
    commentaryDiscoveries,
    capitalAllocationDiscoveries,
    initiativeDiscoveries,
  };
}
