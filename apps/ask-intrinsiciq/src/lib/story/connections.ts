// Evidence connections. Builds chains of nodes from existing records.
// An edge is "Supported" only when records identify the same measured item,
// "Related" when records share a theme/period but nothing proves the link, and
// "Unverified" when the records cannot establish it. Chronology never upgrades an edge.
import { questionRoute } from "@/src/lib/routes";
import { capexProgramme, completedDeals, dealAmount, dealName } from "./capital";
import { registerSourceOf } from "./commitment-evidence";
import { revenueRun } from "./story-events";
import type { StoryInputs } from "./story-adapter";
import { clean, cr, fyNum } from "./text";

export type Relation = "Supported" | "Related" | "Unverified";
export type ConnNode = {
  title: string;
  period: string;
  establishes: string;
  facts: string[];
  evidence: string[];
};
export type ConnEdge = { relation: Relation; note: string };
export type Connection = {
  id: string;
  title: string;
  question: string;
  nodes: ConnNode[];
  edges: ConnEdge[];
  stopNote: string | null;
  link: { label: string; href: string } | null;
};

type Obj = Record<string, unknown>;
const fy = (p: unknown) => (fyNum(String(p ?? "")) === null ? "n/a" : `FY${fyNum(String(p))}`);

// A link to a question page is offered only when that question has an approved answer.
function family(slug: string, id: string, label: string, available: string[]) {
  return available.includes(id) ? { label, href: questionRoute(slug, id) } : null;
}

export function buildConnections(input: StoryInputs): Connection[] {
  const out: Connection[] = [];
  const cases = (input.attribution ?? []) as Obj[];
  const q = (id: string, label: string) => family(input.slug, id, label, input.available);

  // 1 ─ Commitments: promise → reported progress → delivery assessment → economic outcome (approved answers)
  const sourceOf = registerSourceOf(input.commitments);
  for (const r of input.commitmentRows.filter((x) => x.hard && x.hasEvidence)) {
    const numeric = r.observed.length > 0 && r.target !== null;
    out.push({
      id: `conn-${out.length + 1}`,
      title: clean(r.promise),
      question: "Did what was reported move management's commitment towards delivery?",
      nodes: [
        { title: "What management said", period: r.period, establishes: `${clean(r.promise)}${r.timeframe ? ` (${r.timeframe})` : ""}`, facts: [`Tracker status: ${r.states.tracker}`], evidence: [sourceOf(r) ?? "Approved answer: What has management promised?"] },
        { title: "What was reported", period: r.observed.length ? `FY${r.observed[0].fy}–FY${r.observed[r.observed.length - 1].fy}` : r.period, establishes: r.states.execution, facts: r.observed.map((o) => `FY${o.fy}: ${o.value}%${o.calculated ? " (calculated)" : ""}`), evidence: r.evidence.length ? r.evidence : ["Approved answer: What did management actually deliver?"] },
        { title: "Delivery and target", period: r.timeframe || "n/a", establishes: `${r.states.delivery}. ${r.states.target}.`, facts: [], evidence: ["Approved answer: What did management actually deliver?"] },
        { title: "Economic outcome", period: "n/a", establishes: `${r.states.economic}.`, facts: [], evidence: ["Approved answers, FY20–FY26"] },
      ],
      edges: [
        { relation: "Supported", note: "The same commitment in the approved record." },
        numeric ? { relation: "Supported", note: "Arithmetic comparison of the reported figures with the stated target." } : { relation: r.deliveryClass === "unknown" ? "Unverified" : "Related", note: r.deliveryClass === "unknown" ? "The records do not establish whether the reported step met the commitment." : "The reported step is relevant to the commitment, but the deadline and result are not both established." },
        { relation: "Unverified", note: "No economic outcome is confirmed for this commitment; reported progress is not an economic result." },
      ],
      stopNote: r.states.uncertainty[0] ?? "Evidence stops at reported progress; no economic result is shown.",
      link: q("what-did-management-actually-deliver", "Management Delivery"),
    });
  }

  // 2 ─ Acquisitions: transaction → integration evidence → attributable outcome
  const deals = completedDeals(cases);
  if (deals.length) {
    const amount = (d: Obj) => (dealAmount(d) ? cr(dealAmount(d)!) : null);
    const names = deals.map((d) => (amount(d) ? `${dealName(d)!} — ${amount(d)}` : dealName(d)!));
    const anyAmount = deals.some((d) => amount(d));
    const per = fy((deals[0].deployment_periods as string[])[0]);
    const alts = [...new Set(deals.flatMap((d) => (d.alternative_explanations as string[]) ?? []))].slice(0, 3);
    out.push({
      id: `conn-${out.length + 1}`,
      title: `${names.join(" and ")}`,
      question: "Did the acquisitions lead to results the records can attribute to them?",
      nodes: [
        { title: "Transactions completed", period: per, establishes: `${deals.length === 1 ? "A completed transaction is" : `${deals.length} completed transactions are`} recorded${anyAmount ? "." : "; amounts are not in the extracted records."}`, facts: names, evidence: [`Capital-allocation ledger, ${per}`] },
        { title: "Integration or execution", period: "after " + per, establishes: `The records cannot confirm integration or execution of ${deals.length === 1 ? "this deal" : "these deals"}.`, facts: ["Integration evidence: none found"], evidence: [`Capital-allocation ledger, ${per}`] },
        { title: "Attributable financial outcome", period: "n/a", establishes: `No outcome the records can attribute to ${deals.length === 1 ? "this deal" : "these deals"}.`, facts: ["Other explanations to rule out:", ...alts], evidence: [`Economic attribution review, ${per}`] },
      ],
      edges: [
        { relation: "Unverified", note: "No record shows what was done after the deals closed." },
        { relation: "Unverified", note: "Revenue or margin changes cannot be tied to the deals without segment-level disclosure." },
      ],
      stopNote: "Evidence stops at the completed transaction. A completed deal is not evidence of integration or returns.",
      link: q("how-is-capital-allocated", "Capital Allocation"),
    });
  }

  // 4 ─ Strategy → capital → capacity → group results (each link only as strong as the records)
  const capex = capexProgramme(cases);
  const live = (input.projects as Obj[]).filter((p) => (p.assessment as Obj | undefined)?.execution_status === "operational" && String(p.project_name).length >= 12);
  if (capex && live.length) {
    const sorted = live.map((p) => ({ n: String(p.project_name), per: fy(((p.source_references as Obj[]) ?? [])[0]?.period), pg: ((p.source_references as Obj[]) ?? [])[0]?.page })).sort((a, b) => a.per.localeCompare(b.per));
    const theme = input.strategyThemes.find((t) => (t.capital_backed === true || t.capital_backed === "True") && /capital|capacity|manufactur|expansion/i.test(String(t.theme_name)));
    const run = revenueRun(input.revenue);
    const nodes: ConnNode[] = [];
    const edges: ConnEdge[] = [];
    if (theme) {
      nodes.push({ title: "Stated priority", period: fy(theme.first_period), establishes: `${String(theme.theme_name)} is a recorded management priority${theme.current_status === "CURRENT_PRIORITY" ? " and is still current" : `, last confirmed in ${fy(theme.last_confirmed_period)}`}.`, facts: ["Records tag this theme as capital-backed"], evidence: ["Strategy evolution record, annual-report commentary"] });
      edges.push({ relation: "Related", note: "The strategy record tags the theme as capital-backed, but it does not tie specific spending to it." });
    }
    nodes.push({ title: "Capital spent", period: `${capex.span}`, establishes: "Total organic capital expenditure in the ledger.", facts: [cr(capex.amount)], evidence: [`Capital-allocation ledger, ${capex.span}`] });
    edges.push({ relation: "Related", note: "Both are in the same period, but the records do not say which spending built which project." });
    nodes.push({ title: "Projects reported operational", period: [...new Set(sorted.map((s) => s.per))].join(", "), establishes: "Sites and facilities the records report as operating.", facts: sorted.map((s) => `${s.n} (${s.per})`), evidence: sorted.map((s) => `Annual report ${s.per}, p.${s.pg ?? "n/a"}`) });
    if (run.length >= 2) {
      edges.push({ relation: "Unverified", note: "Group revenue cannot be tied to specific sites: no utilisation, capacity or site-level revenue is disclosed." });
      nodes.push({ title: "Group results", period: `FY${fyNum(run[0].year)}–FY${fyNum(run[run.length - 1].year)}`, establishes: "Reported results for the whole company, not for these projects.", facts: [`Revenue ${cr(run[0].value)} → ${cr(run[run.length - 1].value)} (${run[0].basis} basis)`], evidence: [`Financial statements FY${fyNum(run[0].year)}–FY${fyNum(run[run.length - 1].year)}`] });
    } else {
      edges.push({ relation: "Unverified", note: "No utilisation, capacity or incremental revenue is extracted into the records for these projects." });
      nodes.push({ title: "Operating or economic result", period: "n/a", establishes: "No utilisation, capacity or incremental revenue is extracted into the records for these projects.", facts: ["Utilisation: not extracted", "Incremental revenue by site: not extracted"], evidence: ["Economic attribution review"] });
    }
    out.push({
      id: `conn-${out.length + 1}`,
      title: "Capital spent on plants and capacity",
      question: "Did capital spending show up as operating or economic results?",
      nodes, edges,
      stopNote: "Evidence stops at the reported projects. A facility in operation, and revenue growth in the same years, do not show that one produced the other.",
      link: q("how-is-capital-allocated", "Capital Allocation"),
    });
  }

  // 5 ─ Active risks: risk → management response → observable mitigation (same source as the approved risk answer)
  const themes = (input.riskThemes ?? []) as Obj[];
  const latest = Math.max(0, ...themes.map((t) => fyNum(String(t.latest_seen_period)) ?? 0));
  const rank = (t: Obj) => (String(t.current_state) === "WORSENING" ? 0 : 1);
  const active = themes
    .filter((t) => ["WORSENING", "RECURRING"].includes(String(t.current_state)) && (fyNum(String(t.latest_seen_period)) ?? 0) === latest)
    .sort((x, y) => rank(x) - rank(y)).slice(0, 3);
  for (const t of active) {
    const events = ((t.timeline as Obj[]) ?? []).filter((e) => String(e.management_response ?? "").trim());
    const first = events[0];
    const per = `${fy(t.first_seen_period)}–${fy(t.latest_seen_period)}`;
    const word = String(t.current_state).toLowerCase();
    const name = String(t.theme).replace(/^./, (c) => c.toUpperCase());
    const impact = String(t.economic_impact_status ?? "UNPROVEN");
    out.push({
      id: `conn-${out.length + 1}`,
      title: name,
      question: "Is the risk followed by a disclosed response and an observable result?",
      nodes: [
        { title: "The risk", period: per, establishes: clean(String(t.risk_description ?? "")), facts: [`Pattern: ${word}`], evidence: [`Risk evolution timeline, ${per}`] },
        { title: "Management response", period: first ? fy(first.period) : "n/a", establishes: first ? `Recorded in ${fy(first.period)}: “${clean(String(first.management_response))}”.` : "No management response is recorded in the risk timeline.", facts: [first ? "Response: recorded" : "Response: none found"], evidence: [`Risk evolution timeline, ${first ? fy(first.period) : per}`] },
        { title: "Observable mitigation", period: "n/a", establishes: impact === "UNPROVEN" ? "No mitigation result can be observed; the economic effect is not proven." : "A mitigation result is recorded.", facts: [impact === "UNPROVEN" ? "Result: not observable" : "Result recorded"], evidence: [`Risk evolution timeline, ${per}`] },
      ],
      edges: [
        first && String(first.response_identity_basis) === "same_risk_disclosure"
          ? { relation: "Supported", note: "The response appears in the same disclosure as the risk." }
          : { relation: "Unverified", note: first ? "The records do not tie this response to the risk." : "No response is recorded, so there is nothing to connect." },
        { relation: "Unverified", note: "Without an observable result there is nothing to connect the response to." },
      ],
      stopNote: first ? "Evidence stops at the response: no mitigation result can be observed." : "Evidence stops at the risk: a missing disclosure is not evidence that nothing was done.",
      link: q("what-could-go-wrong", "Risks / Diligence"),
    });
  }
  return out;
}
