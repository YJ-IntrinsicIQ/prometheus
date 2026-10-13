import path from "node:path";
import { readJsonIfExists } from "@/src/lib/prometheus/read-json";
import { getRepoRoot } from "@/src/lib/ask-intrinsiciq/paths";
import { COMPANIES } from "@/src/lib/story/companies";
import { fyNum } from "@/src/lib/story/text";

type Obj = Record<string, unknown>;
export type Pt = { fy: number; v: number; basis: string; defn?: string }; // defn: a definition the source line carries (e.g. "cash_and_bank_balances")

// ── Plausibility guards. The records carry some mis-extracted values (e.g. a bank's "days of receivables" or a
// debt-to-equity of 10,000×). A value outside the range a real company could report is treated as missing, never repaired.
const RANGE: Record<string, [number, number]> = {
  debt_to_equity: [0, 20], roe: [-100, 100], roa: [-50, 50], roce: [-100, 200], npm: [-100, 100], opm: [-100, 100], ebitda_margin: [-100, 100],
  cfo_to_pat: [-20, 20], fcf_to_pat: [-20, 20], receivable_days: [0, 1000], inventory_days: [0, 1500], cash_conversion_cycle: [-500, 2000], payout_ratio: [0, 200],
};
const plausible = (metric: string, v: number) => Number.isFinite(v) && (!RANGE[metric] || (v >= RANGE[metric][0] && v <= RANGE[metric][1]));

export type PanelData = {
  years: number[];
  series: (group: string, metric: string) => Pt[];
  /** the latest stretch of consecutive years on ONE stated basis: the only years that may be compared */
  run: (group: string, metric: string) => Pt[];
  latest: (group: string, metric: string) => Pt | null;
  ownerEarnings: Obj[];
  perShare: Obj[];
  roi: Obj[];
  workingCapital: { applicability: string; reason: string; rows: Obj[] };
  model: { what: string; customers: string[]; engines: { name: string; type: string; share: number | null; growth: number | null; revenue: number | null; period: string }[]; enginesAvailable: boolean; revenueEngines: string[] };
};

export async function loadPanelData(slug: string, opts: { repoRoot?: string } = {}): Promise<PanelData | null> {
  const company = COMPANIES[slug];
  if (!company) return null;
  const mem = path.join(opts.repoRoot ?? getRepoRoot(), "companies", company.key, "company_memory");
  const [trends, oe, ps, roi, wc, model] = await Promise.all([
    readJsonIfExists<{ years_covered?: string[]; trend_groups?: Record<string, Record<string, { series?: { year: string; value: number; basis?: string; warnings?: string[] }[] }>> }>(path.join(mem, "financials", "financial_trends.json")),
    readJsonIfExists<{ bridges?: Obj[] }>(path.join(mem, "financials", "investor_financial_modules", "owner_earnings_bridge.json")),
    readJsonIfExists<{ analysis?: Obj[] }>(path.join(mem, "financials", "investor_financial_modules", "per_share_compounding_analysis.json")),
    readJsonIfExists<{ entries?: Obj[] }>(path.join(mem, "financials", "investor_financial_modules", "capital_allocation_roi_ledger.json")),
    readJsonIfExists<{ drilldown?: Obj[]; working_capital_applicability?: string; applicability_reason?: string }>(path.join(mem, "financials", "investor_financial_modules", "working_capital_quality_drilldown.json")),
    readJsonIfExists<{ current_business_model?: Obj; customers?: Obj[]; revenue_engines?: Obj[]; economic_engines?: { coverage_status?: string; engines?: { engine_name: string; engine_type: string; history: Obj[] }[] } }>(path.join(mem, "company_model", "company_model.json")),
  ]);
  const series = (group: string, metric: string): Pt[] =>
    (trends?.trend_groups?.[group]?.[metric]?.series ?? [])
      .filter((p) => p.value !== null && plausible(metric, Number(p.value)))
      .map((p) => ({ fy: fyNum(p.year) ?? 0, v: Number(p.value), basis: String(p.basis ?? "unknown"), defn: /definition:(\w+)/.exec((p.warnings ?? []).join("|"))?.[1] }))
      .sort((a, b) => a.fy - b.fy);
  const run = (group: string, metric: string): Pt[] =>
    [...series(group, metric)].reverse().reduce<Pt[]>((acc, p) => (acc.length === 0 ? (p.basis === "unknown" ? acc : [p]) : acc[0].fy - 1 === p.fy && acc[0].basis === p.basis ? [p, ...acc] : acc), []);
  const engines = model?.economic_engines?.coverage_status === "SUPPORTED" ? (model.economic_engines.engines ?? []) : [];
  const lastOf = (e: { history: Obj[] }) => e.history[e.history.length - 1] ?? {};
  const customers = (model?.customers ?? []).map((c) => String(c.customer_segment_id ?? "").replace(/_/g, " ")).filter(Boolean);
  return {
    years: (trends?.years_covered ?? []).map((y) => fyNum(y) ?? 0),
    series,
    run,
    latest: (g, m) => { const s = series(g, m); return s.length ? s[s.length - 1] : null; },
    ownerEarnings: oe?.bridges ?? [],
    perShare: ps?.analysis ?? [],
    roi: roi?.entries ?? [],
    workingCapital: { applicability: String(wc?.working_capital_applicability ?? "unknown"), reason: String(wc?.applicability_reason ?? ""), rows: wc?.drilldown ?? [] },
    model: {
      what: String(model?.current_business_model?.what_company_does ?? model?.current_business_model?.summary ?? ""),
      customers,
      enginesAvailable: engines.length > 0,
      engines: engines.map((e) => ({ name: e.engine_name, type: e.engine_type, share: (lastOf(e).revenue_share as number | null) ?? null, growth: (lastOf(e).growth_rate as number | null) ?? null, revenue: (lastOf(e).revenue_crore as number | null) ?? null, period: String(lastOf(e).reporting_period ?? "") })),
      revenueEngines: (model?.revenue_engines ?? []).map((r) => String(r.description ?? "")).filter(Boolean),
    },
  };
}
