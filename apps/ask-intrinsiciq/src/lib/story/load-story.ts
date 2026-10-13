import path from "node:path";
import { readJsonIfExists } from "@/src/lib/prometheus/read-json";
import { getRepoRoot } from "@/src/lib/ask-intrinsiciq/paths";
import { availableAnnualReports } from "@/src/lib/evidence/documents";
import { buildStory, type Story, type StoryInputs } from "./story-adapter";
import { COMPANIES } from "./companies";
import { approvedQuestionIds } from "./authorization";
import { QUESTIONS } from "./questions";
import { loadApprovedAnswers } from "./approved-answers";
import { parseCommitmentEvidence } from "./commitment-evidence";
import { fyNum } from "./text";
import { loadCatalog } from "@/src/lib/catalog/catalog";
import { loadAbsenceLedger, withAbsence } from "@/src/lib/provenance/absence";
import { servedId } from "@/src/lib/catalog/journey";

type LoadOptions = { repoRoot?: string };
type Obj = Record<string, unknown>;
type Trend = { series?: { year: string; value: number; basis?: string }[] };

// Read-only. Everything is read from the company's own folder; nothing is shared between companies.
export async function loadStoryInputs(slug: string, opts: LoadOptions = {}): Promise<StoryInputs | null> {
  const company = COMPANIES[slug];
  if (!company) return null;
  const root = opts.repoRoot ?? getRepoRoot();
  const mem = path.join(root, "companies", company.key, "company_memory");
  const [commitments, projects, attribution, risks, strategy, trends, answers, available] = await Promise.all([
    readJsonIfExists<{ commitments?: StoryInputs["commitments"] }>(path.join(mem, "management_commitments", "management_commitments.json")),
    readJsonIfExists<{ projects?: StoryInputs["projects"] }>(path.join(mem, "projects", "projects_registry.json")),
    readJsonIfExists<{ cases?: StoryInputs["attribution"] }>(path.join(mem, "economic_attribution", "economic_attribution_intelligence.json")),
    readJsonIfExists<{ risk_themes?: StoryInputs["riskThemes"] }>(path.join(mem, "gold", "risk_evolution_timeline.json")),
    readJsonIfExists<{ strategy_themes?: Obj[]; data_coverage?: { latest_period?: string } }>(path.join(mem, "gold", "strategy_evolution_timeline.json")),
    readJsonIfExists<{ years_covered?: string[]; trend_groups?: { revenue_and_income?: { revenue?: Trend }; profitability?: { pat?: Trend } } }>(path.join(mem, "financials", "financial_trends.json")),
    loadApprovedAnswers(slug, { repoRoot: root }),
    approvedQuestionIds(slug),
  ]);
  const catalog = await loadCatalog({ repoRoot: root });
  const titles: Record<string, string> = {};   // only approved questions are named, so no title is offered for an unavailable answer
  for (const q of catalog.questions) if (available.includes(servedId(q))) titles[servedId(q)] ??= (QUESTIONS.find((x) => x.id === servedId(q))?.title ?? q.title);
  // Commitment evidence is taken only from approved answers.
  const series = (t?: Trend) => (t?.series ?? []).map((p) => ({ year: String(p.year), value: Number(p.value), basis: String(p.basis ?? "unknown") }));
  const years = (trends?.years_covered ?? []).map((y) => fyNum(y) ?? 0);
  return {
    slug,
    key: company.key,
    company: company.name,
    latestYear: fyNum(strategy?.data_coverage?.latest_period) ?? Math.max(0, ...years),
    withholdCommitments: company.withholdCommitmentRegister === true,
    available,
    titles,
    docs: availableAnnualReports(slug),
    commitments: commitments?.commitments ?? [],
    projects: projects?.projects ?? [],
    attribution: attribution?.cases ?? [],
    riskThemes: risks?.risk_themes ?? [],
    strategyThemes: strategy?.strategy_themes ?? [],
    revenue: series(trends?.trend_groups?.revenue_and_income?.revenue),
    pat: series(trends?.trend_groups?.profitability?.pat),
    commitmentRows: parseCommitmentEvidence(answers["what-has-management-promised"] ?? null, answers["what-did-management-actually-deliver"] ?? null, commitments?.commitments ?? []),
  };
}

export async function loadStory(slug: string, opts: LoadOptions = {}): Promise<Story | null> {
  const inputs = await loadStoryInputs(slug, opts);
  return inputs ? withAbsence(buildStory(inputs), await loadAbsenceLedger(slug, opts)) : null;
}
