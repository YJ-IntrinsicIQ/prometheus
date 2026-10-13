// Story events built from existing records. Each builder states what a record says and, in a fixed hedged template,
// what that kind of record does and does not show. None infers an outcome from an action: an acquisition, a plant or a
// launch is reported as an action, and the page says when no result can be attributed to it.
import { capexProgramme, completedDeals, dealAmount, dealName, divestments, pendingDeals } from "./capital";
import type { CommitmentRow } from "./commitment-evidence";
import { commitmentDeadline } from "./accountability";
import { clean, cr, firstSentence, fyLabel, fyNum, sentenceCase } from "./text";

type Obj = Record<string, unknown>;

export type StoryCategory = "Strategy" | "Investment" | "Execution" | "Outcome" | "Risk";
export type StoryKind = "Management statement" | "Confirmed activity" | "Reported result" | "Risk disclosure";
export type RawEvent = {
  key: string;
  period: string;
  sortKey: number;
  category: StoryCategory;
  kind: StoryKind;
  headline: string;
  summary: string;
  original?: string;
  interpretation: { happened: string; matters: string; unproven: string };
  evidence: string[];
  limitations: string[];
  priority: number;
  commitment?: CommitmentRow["states"];
  related?: { key: string; note: string }[];
};

export type Series = { year: string; value: number; basis: string }[];

const INTERP = {
  statement: "A stated target gives investors a benchmark to check against later reports.",
  theme: "A priority that persists across reports signals durable intent; whether it produced results is a separate question.",
  deal: "Acquisitions change what the company owns; whether they add value only shows up in later results.",
  capex: "Capital spending builds capacity; it is not by itself evidence of returns.",
  project: "A facility in operation is a precondition for output, not proof of returns.",
  risk: "A risk that is new or worsening is a diligence question; disclosure alone does not show financial impact.",
  result: "These are the reported scale and profitability of the whole group, not of any single decision.",
};
const NOT_CAUSAL = "Dates show what happened when; they do not show that one event caused another.";

// ── Strategy: priorities, and priorities that stopped being reconfirmed ──
export function strategyEvents(themes: Obj[]): RawEvent[] {
  const out: RawEvent[] = [];
  themes.forEach((t, i) => {
    const name = String(t.theme_name ?? "").trim();
    const first = fyNum(String(t.first_period));
    if (!name || first === null) return;
    const last = fyNum(String(t.last_confirmed_period)) ?? first;
    const backed = t.capital_backed === true || t.capital_backed === "True";
    const executed = t.execution_evidence === true || t.execution_evidence === "True";
    const current = t.current_status === "CURRENT_PRIORITY";
    const span = `FY${first}–FY${last}`;
    const key = `strategy-${i}`;
    out.push({
      key, period: `FY${first}`, sortKey: first, category: "Strategy", kind: "Management statement",
      headline: `Priority: ${name}`,
      summary: `${name} is recorded as a management priority from FY${first}${current ? " and is still a current priority" : `, last confirmed in FY${last}`}. ${backed ? "The records show capital deployed under this theme" : "The records show no capital deployed under this theme"}${executed ? " and execution evidence." : "."}`,
      interpretation: {
        happened: `${name} appears in management's reports for ${span}.`,
        matters: INTERP.theme,
        unproven: backed ? "Capital is recorded under this theme; what it returned is not shown." : "Without recorded capital or execution, the priority is a statement of intent.",
      },
      evidence: [`Strategy evolution record, ${span} annual-report commentary`],
      limitations: [],
      priority: 4 + (backed && executed ? 1 : 0),
    });
    if (!current && last < 26)
      out.push({
        key: `${key}-lapsed`, period: `After FY${last}`, sortKey: last + 0.5, category: "Strategy", kind: "Management statement",
        headline: `Priority not reconfirmed: ${name}`,
        summary: `${name} is not described as a priority in the reports after FY${last}. This is not evidence that the work stopped.`,
        interpretation: {
          happened: `After FY${last}, management's reports no longer present ${name.toLowerCase()} as a priority.`,
          matters: "A change in stated priorities is worth asking about: it can mean the work was finished, folded into another theme, or dropped.",
          unproven: "The records do not say which. Silence in the reports is not a negative finding.",
        },
        evidence: [`Strategy evolution record, ${span} annual-report commentary`],
        limitations: [],
        priority: 4,
        related: [{ key, note: "The same priority in the strategy record" }],
      });
  });
  return out;
}

// ── Investment: completed deals, divestments, the capex programme ──
export function investmentEvents(cases: Obj[], latestRevenue: number | null): RawEvent[] {
  const out: RawEvent[] = [];
  const byPeriod = new Map<string, Obj[]>();
  for (const d of completedDeals(cases)) {
    const p = String((d.deployment_periods as string[])[0]);
    byPeriod.set(p, [...(byPeriod.get(p) ?? []), d]);
  }
  for (const [p, ds] of byPeriod) {
    const names = [...new Set(ds.map((d) => (dealAmount(d) ? `${dealName(d)} (${cr(dealAmount(d)!)})` : dealName(d)!)))];
    out.push({
      key: `deal-${p}`, period: fyLabel(p), sortKey: fyNum(p) ?? 0, category: "Investment", kind: "Confirmed activity",
      headline: `${names.length === 1 ? "Acquisition completed" : `${names.length} acquisitions completed`}: ${names.join(" and ")}`,
      summary: `The capital-allocation ledger records ${names.length === 1 ? "a completed acquisition" : "completed acquisitions"} in ${fyLabel(p)}: ${names.join("; ")}.`,
      interpretation: {
        happened: `Completed transactions are recorded in ${fyLabel(p)}: ${names.join("; ")}.`,
        matters: INTERP.deal,
        unproven: "No integration evidence, financial contribution or operating outcome can be attributed to these transactions in the records.",
      },
      evidence: [`Capital-allocation ledger, ${fyLabel(p)}`],
      limitations: ["Amounts are shown only where the ledger states them."],
      priority: 5,
    });
  }
  for (const d of pendingDeals(cases)) {
    const p = String((d.deployment_periods as string[] | undefined)?.[0] ?? "");
    const target = dealName(d)!;
    const terms = d.transaction_terms ? ` Stated terms: ${String(d.transaction_terms)}.` : "";
    const basis = d.transaction_status_basis ? ` The filing states the transaction ${String(d.transaction_status_basis)}.` : "";
    out.push({
      key: `pending-deal-${p}-${target}`, period: fyLabel(p), sortKey: fyNum(p) ?? 0, category: "Investment", kind: "Confirmed activity",
      headline: `Acquisition signed, not completed: ${target}`,
      summary: `The capital-allocation ledger records a transaction that is signed but not completed.${terms}${basis}`.trim(),
      interpretation: {
        happened: `${target} is recorded as a signed, not completed, acquisition.${terms}${basis}`.trim(),
        matters: INTERP.deal,
        unproven: "Completion, the final price paid and any financial contribution cannot be stated until the filing reports them.",
      },
      evidence: [`Capital-allocation ledger, ${fyLabel(p)}`],
      limitations: ["Terms are shown as stated, in the stated currency."],
      priority: 5,
    });
  }
  for (const d of divestments(cases)) {
    const p = String((d.deployment_periods as string[])[0]);
    const what = clean(String(d.action_description)).replace(/\s*\([^)]*\)\s*$/, "");
    out.push({
      key: `divest-${p}`, period: fyLabel(p), sortKey: fyNum(p) ?? 0, category: "Investment", kind: "Confirmed activity",
      headline: `Divestment completed: ${firstSentence(what, 110)}`,
      summary: `The ledger records a completed divestment in ${fyLabel(p)}${dealAmount(d) ? ` (${cr(dealAmount(d)!)})` : ""}.`,
      interpretation: {
        happened: `${sentenceCase(what)} is recorded as completed in ${fyLabel(p)}.`,
        matters: "A sale changes what the company owns and what it reports; the reason and the financial effect matter more than the transaction.",
        unproven: "The records do not show why the business was sold or what it contributed before the sale.",
      },
      evidence: [`Capital-allocation ledger, ${fyLabel(p)}`],
      limitations: [],
      priority: 5,
    });
  }
  const capex = capexProgramme(cases);
  if (capex) {
    const share = latestRevenue ? capex.amount / latestRevenue : null;
    out.push({
      key: "capex", period: `${capex.span}`, sortKey: capex.last, category: "Investment", kind: "Confirmed activity",
      headline: `Organic capital spending recorded: ${capex.label}`,
      summary: `The capital-allocation ledger records ${capex.label} of organic capital expenditure (plants, capacity and equipment).`,
      interpretation: {
        happened: `Organic capex of ${capex.label} is recorded in the ledger.`,
        matters: INTERP.capex,
        unproven: "The ledger does not say which spending built which site, or what any site earned.",
      },
      evidence: [`Capital-allocation ledger, ${capex.span}`],
      limitations: [],
      priority: share === null ? 3 : share >= 0.05 ? 5 : share >= 0.01 ? 4 : 3,
    });
  }
  return out;
}

/** The latest stretch of consecutive years reported on one stated basis: the only years that may be compared. */
export function revenueRun(r: Series): Series {
  const y = (s: string) => fyNum(s) ?? 0;
  return [...r].reverse().reduce<Series>((acc, x) => (acc.length === 0 || (y(acc[0].year) - 1 === y(x.year) && x.basis === acc[0].basis && x.basis !== "unknown") ? [x, ...acc] : acc), []);
}

// ── Outcome: the reported results, compared only where the basis is the same and the years are consecutive ──
export function outcomeEvents(rev: Series, pat: Series): RawEvent[] {
  const known = (s: Series) => s.filter((p) => Number.isFinite(p.value));
  const r = known(rev), p = known(pat);
  if (!r.length) return [];
  const last = r[r.length - 1];
  const y = (s: string) => fyNum(s) ?? 0;
  const prev = r.find((x) => y(x.year) === y(last.year) - 1 && x.basis === last.basis && last.basis !== "unknown");
  const run = revenueRun(r);
  const basisNote = last.basis === "unknown" ? " The records do not say whether the figure is consolidated or standalone." : "";
  const patLast = p.find((x) => y(x.year) === y(last.year));
  const pct = (a: number, b: number) => `${a >= b ? "up" : "down"} ${Math.abs(Math.round(((a - b) / Math.abs(b)) * 100))}%`;
  const bits = [`revenue ${cr(last.value)}${prev ? ` (${pct(last.value, prev.value)} on ${fyLabel(prev.year)})` : ""}`, patLast ? `profit ${cr(patLast.value)}` : ""].filter(Boolean);
  const out: RawEvent[] = [{
    key: "results-latest", period: fyLabel(last.year), sortKey: y(last.year), category: "Outcome", kind: "Reported result",
    headline: `${fyLabel(last.year)} reported results: ${bits.join(", ")}`,
    summary: `Reported for ${fyLabel(last.year)}: ${bits.join("; ")}.${basisNote}`,
    interpretation: { happened: `Reported for ${fyLabel(last.year)}: ${bits.join("; ")}.`, matters: INTERP.result, unproven: `${NOT_CAUSAL} They do not show what drove these figures.${basisNote}` },
    evidence: [`Financial statements ${fyLabel(last.year)}`],
    limitations: last.basis === "unknown" ? ["Reporting basis not yet identified in the extracted records."] : [],
    priority: 4,
  }];
  if (run.length >= 4) {
    const first = run[0];
    const pf = p.find((x) => y(x.year) === y(first.year) && x.basis === first.basis);
    out.unshift({
      key: "results-arc", period: `${fyLabel(first.year)}–${fyLabel(last.year)}`, sortKey: y(last.year) - 0.4, category: "Outcome", kind: "Reported result",
      headline: `Revenue moved from ${cr(first.value)} (${fyLabel(first.year)}) to ${cr(last.value)} (${fyLabel(last.year)})`,
      summary: `On the same ${last.basis} basis, reported revenue went from ${cr(first.value)} to ${cr(last.value)} (${pct(last.value, first.value)} over ${run.length - 1} years)${pf && patLast ? `; profit from ${cr(pf.value)} to ${cr(patLast.value)}` : ""}.`,
      interpretation: { happened: `Revenue ${pct(last.value, first.value)} between ${fyLabel(first.year)} and ${fyLabel(last.year)}.`, matters: INTERP.result, unproven: `${NOT_CAUSAL} The records do not attribute this growth to any investment, acquisition or product.` },
      evidence: [`Financial statements ${fyLabel(first.year)}–${fyLabel(last.year)}`],
      limitations: [],
      priority: 6,
    });
  }
  return out;
}

// ── Risk: new and worsening themes ──
export function riskEvents(themes: Obj[]): RawEvent[] {
  const latest = Math.max(0, ...themes.map((t) => fyNum(String(t.latest_seen_period)) ?? 0));
  return themes
    .filter((t) => ["NEW", "WORSENING"].includes(String(t.current_state)) && (fyNum(String(t.latest_seen_period)) ?? 0) >= latest - 1)
    .sort((a, b) => Number(String(b.current_state) === "WORSENING") - Number(String(a.current_state) === "WORSENING"))
    .slice(0, 2)
    .map((t, i) => {
      const name = sentenceCase(String(t.theme));
      const isNew = String(t.current_state) === "NEW";
      const per = `${fyLabel(String(t.first_seen_period))}–${fyLabel(String(t.latest_seen_period))}`;
      const response = ((t.timeline as Obj[] | undefined) ?? []).find((e) => String(e.management_response ?? "").trim());
      return {
        key: `risk-${i}`, period: fyLabel(String(isNew ? t.first_seen_period : t.latest_seen_period)), sortKey: fyNum(String(isNew ? t.first_seen_period : t.latest_seen_period)) ?? 0,
        category: "Risk" as const, kind: "Risk disclosure" as const,
        headline: `${isNew ? "New risk disclosed" : "Risk worsening"}: ${firstSentence(name, 90)}`,
        summary: firstSentence(String(t.risk_description ?? name), 200),
        interpretation: {
          happened: `${name} is ${isNew ? "disclosed for the first time" : "described as worsening"} (${per}).`,
          matters: INTERP.risk,
          unproven: `${String(t.economic_impact_status ?? "UNPROVEN") === "UNPROVEN" ? "No financial impact is proven in the records. " : ""}${response ? `A management response is recorded (${fyLabel(String(response.period))}).` : "No management response is recorded."}`,
        },
        evidence: [`Risk evolution timeline, ${per}`],
        limitations: [],
        priority: isNew ? 4 : 5,
      };
    });
}

// ── Commitments: promise → reported progress, with the six states kept apart ──
export function commitmentEvents(rows: CommitmentRow[], sourceOf: (r: CommitmentRow) => string | null): RawEvent[] {
  const out: RawEvent[] = [];
  rows.filter((r) => r.hard).forEach((r, i) => {
    const y = fyNum(r.period) ?? 0;
    const lastObs = r.observed[r.observed.length - 1];
    const filing = r.states.execution.match(/FY(\d{2})/)?.[1];
    const progressYear = lastObs?.fy ?? (filing ? Number(filing) : y);
    const base = `commitment-${i}`;
    const short = firstSentence(r.promise, 100);
    const source = sourceOf(r);
    out.push({
      key: `${base}-promise`, period: r.period, sortKey: y, category: "Strategy", kind: "Management statement",
      headline: `Commitment: ${short}${r.timeframe ? ` (${r.timeframe})` : ""}`,
      original: r.promise,
      summary: `Management set a specific target${r.timeframe ? ` with a deadline of ${r.timeframe}` : ""}. The commitment tracker records it as ${r.states.tracker.toLowerCase()}; that is a tracking status, not a finding that nothing happened.`,
      interpretation: { happened: `In ${r.period}, management committed to: ${r.promise}${r.timeframe ? ` (${r.timeframe})` : ""}.`, matters: INTERP.statement, unproven: r.states.uncertainty[0] ?? "Whether the target was met is not shown in the records." },
      evidence: source ? [source] : [`Approved answer: What has management promised?`],
      limitations: [],
      priority: 5,
      commitment: r.states,
      related: r.hasEvidence ? [{ key: `${base}-progress`, note: "The same commitment: reported progress" }] : [],
    });
    if (!r.hasEvidence) return; // no later evidence: the promise is shown, and no "progress" event is invented
    out.push({
      key: `${base}-progress`, period: `FY${progressYear}`, sortKey: progressYear + 0.1, category: "Execution", kind: "Confirmed activity",
      headline: progressHeadline(r),
      summary: `${r.states.execution}. ${r.states.target}. ${r.states.delivery}.`,
      interpretation: {
        happened: `${r.states.execution}.`,
        matters: "Reported progress shows execution against a stated target; it is not the same as an economic result.",
        unproven: `${r.states.uncertainty[0] ?? "Economic outcome: " + r.states.economic.toLowerCase() + "."}`,
      },
      evidence: r.evidence.length ? r.evidence : [`Approved answer: What did management actually deliver?`],
      limitations: [],
      priority: 6,
      commitment: r.states,
      related: [{ key: `${base}-promise`, note: "The same commitment: what management promised" }],
    });
  });
  return out;
}

function progressHeadline(r: CommitmentRow): string {
  const last = r.observed[r.observed.length - 1];
  const subject = firstSentence(r.promise, 70);
  const note = r.deliveryClass === "partly" ? " — deadline and approval not established" : "";
  if (!last) return `${subject}: ${r.states.execution.replace(/^./, (c) => c.toLowerCase())}${note}`;
  const series = r.observed.map((o) => `${o.value}%`).join(" → ");
  const verdict = r.deliveryClass === "reached" ? "target level reported reached" : r.deliveryClass === "in_progress" ? "deadline not yet reached" : "";
  return `${subject}: ${series} (FY${r.observed[0].fy}–FY${last.fy})${verdict ? ` — ${verdict}` : ""}`;
}

// ── Register-based commitments (companies whose register is not withheld) ──
export function registerCommitmentEvents(commitments: Obj[], latestYear: number): RawEvent[] {
  const seen = new Set<string>();
  const out: RawEvent[] = [];
  for (const m of commitments) {
    if (m.verification_applicability !== "APPLICABLE") continue;
    const fp = String(m.commitment_fingerprint ?? m.id);
    if (seen.has(fp)) continue;
    seen.add(fp);
    const canonical = commitmentDeadline(m);
    const frame = String(m.expected_timeframe ?? "");
    const by = /(?:by\s+)?(20\d{2})|FY\s?(\d{4})/i.exec(frame.replace(/FY\s?(\d{4})/i, "$1"));
    const dueYear = (m.commitment_basis ? canonical?.year : by ? Number(by[1] ?? by[2]) : null) ?? null;
    const passed = dueYear !== null && dueYear - 2000 <= latestYear;
    const y = fyNum(String(m.announcement_period)) ?? 0;
    const stmt = clean(String(m.original_statement ?? ""));
    const refs = (m.source_references as Obj[] | undefined) ?? [];
    const deadline = dueYear ? `by ${dueYear}` : "no deadline stated";
    out.push({
      key: `register-${out.length}`, period: fyLabel(String(m.announcement_period)), sortKey: y, category: "Strategy", kind: "Management statement",
      headline: `Commitment: ${firstSentence(stmt, 110)}`,
      summary: `A specific, checkable commitment (${deadline}). The commitment tracker records it as ${String(m.status ?? "unable to verify").toLowerCase()}${passed ? "; the deadline has passed and the records hold no delivery confirmation — unverified, not missed" : ""}.`,
      original: stmt,
      interpretation: { happened: `In ${fyLabel(String(m.announcement_period))}, management stated: ${stmt}`, matters: INTERP.statement, unproven: "No later evidence in the records confirms or contradicts this commitment. Missing disclosure is not counted as failure." },
      evidence: [`Annual report FY${y}, p.${refs[0]?.page ?? "n/a"}`],
      limitations: ["Tracker status only; no execution evidence is linked to this commitment."],
      priority: passed ? 5 : dueYear ? 4 : 3,
      commitment: {
        tracker: sentenceCase(String(m.status ?? "unable to verify").toLowerCase()),
        execution: "No execution evidence linked in the records",
        delivery: "Not established in the records",
        target: passed ? "Deadline passed; no delivery confirmation in the records" : dueYear ? "Deadline not yet reached" : "No measurable target or deadline",
        economic: "Not established in the records",
        uncertainty: ["Whether this was delivered is not shown in the records."],
      },
    });
  }
  return out;
}
