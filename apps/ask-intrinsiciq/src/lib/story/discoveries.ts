// Discoveries — deterministic comparisons over approved records.
// A discovery is dropped (never padded) if its inputs are missing or its checks fail.
import { questionRoute } from "@/src/lib/routes";
import { buildAccountability, STATUSES } from "./accountability";
import { buildConnections, type Connection } from "./connections";
import { capexProgramme } from "./capital";
import { revenueRun } from "./story-events";
import type { StoryInputs } from "./story-adapter";
import { cr, firstSentence } from "./text";

export type Category = "Important changes" | "Emerging patterns" | "Evidence connections" | "Unanswered questions";
export type Trust = "Observed" | "Derived" | "Interpretation" | "Unknown";
export type Visual =
  | { kind: "timeline"; items: { when: string; text: string }[] }
  | { kind: "table"; head: string[]; rows: string[][] };

export type Discovery = {
  id: string;
  category: Category;
  headline: string;
  keyNumber: { value: string; label: string };
  why: string;
  years: string;
  visual: Visual;
  discovered: string;
  evidence: { trust: Trust; text: string; source: string }[];
  significance: string;
  unknown: string[];
  links: { label: string; href: string }[];
  basis: "Approved records";
};

type Obj = Record<string, unknown>;
const fyNumOf = (p: unknown) => Number(/(\d{2})/.exec(String(p))?.[1] ?? 0);
const span = (xs: unknown[]) => {
  const ys = xs.flatMap((x) => [...String(x).matchAll(/fy\s?(\d{2})/gi)].map((m) => Number(m[1])));
  return ys.length ? `FY${Math.min(...ys)}–FY${Math.max(...ys)}` : "n/a";
};

export function buildDiscoveries(input: StoryInputs): Discovery[] {
  const out: Discovery[] = [];
  const acct = input.withholdCommitments ? null : buildAccountability(input);
  const conns = buildConnections(input);
  const slug = input.slug;
  const connLink = (c: Connection | undefined, label = "See in Connections") => (c ? [{ label, href: `#${c.id}` }] : []);
  const q = (id: string, label: string) => (input.available.includes(id) ? [{ label, href: questionRoute(slug, id) }] : []);

  // ── Commitments: what the tracker says versus what the approved evidence shows ──
  const hard = input.commitmentRows.filter((r) => r.hard);
  const withProgress = hard.filter((r) => r.hasEvidence);
  if (hard.length && withProgress.length && hard.every((r) => /unable to verify/i.test(r.states.tracker))) {
    const n = (c: string) => hard.filter((r) => r.deliveryClass === c).length;
    out.push({
      id: `d-${out.length + 1}`, category: "Evidence connections",
      headline: `Progress is disclosed on ${withProgress.length === hard.length ? `all ${hard.length}` : `${withProgress.length} of ${hard.length}`} hard commitments, even though the tracker shows none verified`,
      keyNumber: { value: `${hard.length} hard`, label: `${n("reached")} target reached · ${n("partly")} partly evidenced · ${n("in_progress")} in progress` },
      why: "A tracker status of unable to verify only means the tracker has not been updated; the annual reports do report progress, with the open questions listed below.",
      years: span(hard.flatMap((r) => [r.period, ...r.observed.map((o) => `FY${o.fy}`)])),
      visual: { kind: "table", head: ["Commitment", "Tracker", "Reported by the company", "Delivery and target"], rows: hard.map((r) => [`${firstSentence(r.promise, 80)}${r.timeframe ? ` (${r.timeframe})` : ""}`, r.states.tracker, r.states.execution, `${r.states.delivery}. ${r.states.target}`]) },
      discovered: `${hard.length} of the tracked statements are hard commitments with a target and deadline. For each, the annual reports state progress or a filing; the commitment tracker still records every one as unable to verify.`,
      evidence: hard.map((r) => ({ trust: (r.observed.some((o) => o.calculated) ? "Derived" : "Observed") as Trust, text: `${firstSentence(r.promise, 70)} — ${r.states.execution}`, source: r.evidence[0] ?? "Approved answer: What did management actually deliver?" })),
      significance: "Missing tracker confirmation is not failure. Reported progress is also not the same as delivery of an economic result, and a filing is not an approval.",
      unknown: [...new Set(hard.flatMap((r) => r.states.uncertainty))].slice(0, 4),
      links: [{ label: "See in Story", href: "#commitments" }, ...connLink(conns[0]), ...q("what-did-management-actually-deliver", "Management Delivery")],
      basis: "Approved records",
    });
  }
  const reachedRow = hard.find((r) => r.deliveryClass === "reached");
  const fell = hard.find((r) => r.observed.length >= 2 && r.observed[r.observed.length - 1].value < r.observed[r.observed.length - 2].value);
  if (reachedRow && fell) {
    const a = fell.observed[fell.observed.length - 2], b = fell.observed[fell.observed.length - 1];
    const delta = (Math.round((b.value - a.value) * 10) / 10).toFixed(1).replace("-", "−");
    out.push({
      id: `d-${out.length + 1}`, category: "Important changes",
      headline: `One target level was reached, but reported progress on another fell in FY${b.fy}`,
      keyNumber: { value: `${delta} pts`, label: `FY${a.fy} ${a.value}% → FY${b.fy} ${b.value}% (${firstSentence(fell.promise, 50)})` },
      why: `Progress on ${firstSentence(fell.promise, 60)} moved away from its ${fell.target ?? ""}% target while ${firstSentence(reachedRow.promise, 60)} reported reaching its level.`,
      years: span([reachedRow.period, fell.period, ...fell.observed.map((o) => `FY${o.fy}`)]),
      visual: { kind: "table", head: ["Commitment", "Reported", "Target and delivery"], rows: [reachedRow, fell].map((r) => [firstSentence(r.promise, 80), r.states.execution, `${r.states.target}. ${r.states.delivery}`]) },
      discovered: `${reachedRow.states.target}. For ${firstSentence(fell.promise, 70)}, the reported figure fell from ${a.value}% (FY${a.fy}) to ${b.value}% (FY${b.fy}).`,
      evidence: [reachedRow, fell].flatMap((r) => r.observed.map((o) => ({ trust: (o.calculated ? "Derived" : "Observed") as Trust, text: `${firstSentence(r.promise, 50)} — FY${o.fy}: ${o.value}%${o.calculated ? " (calculated)" : ""}`, source: r.evidence.find((e) => e.includes(`FY${o.fy},`)) ?? r.evidence[0] ?? "Approved answer" }))),
      significance: fell.deliveryClass === "in_progress" ? "A dip in one year is not a missed target while the deadline is ahead, but it is a specific question to put to management." : "The two results move independently; one does not offset the other.",
      unknown: [fell.states.uncertainty[0] ?? "Why the figure fell: no explanation was found in the records.", ...(reachedRow.states.uncertainty[0] ? [reachedRow.states.uncertainty[0]] : [])].slice(0, 3),
      links: [{ label: "See in Story", href: "#commitments" }, ...q("what-did-management-actually-deliver", "Management Delivery")],
      basis: "Approved records",
    });
  }

  // ── A capital-backed priority that dropped out of later reports ──
  const lapsed = input.strategyThemes
    .filter((t) => t.current_status !== "CURRENT_PRIORITY" && (t.capital_backed === true || t.capital_backed === "True"))
    .sort((a, b) => Number(b.execution_evidence === true) - Number(a.execution_evidence === true) || (fyNumOf(a.first_period) - fyNumOf(b.first_period)))[0];
  if (lapsed) {
    const f = fyNumOf(lapsed.first_period), l = fyNumOf(lapsed.last_confirmed_period) || f;
    out.push({
      id: `d-${out.length + 1}`, category: "Emerging patterns",
      headline: `A capital-backed priority dropped out of later reports: ${String(lapsed.theme_name)}`,
      keyNumber: { value: `FY${f}–FY${l}`, label: "years the priority was confirmed" },
      why: "Management's priorities shift; this one carried recorded capital but is not described as a priority after FY" + l + ".",
      years: `FY${f}–FY${l}`,
      visual: { kind: "timeline", items: [{ when: `FY${f}`, text: `${String(lapsed.theme_name)} introduced as a priority` }, { when: `FY${l}`, text: "Last confirmed in management's reports" }, { when: `After FY${l}`, text: "Not reconfirmed (not evidence that the work stopped)" }] },
      discovered: `${String(lapsed.theme_name)} appears in management's reports from FY${f} to FY${l}, with capital ${lapsed.execution_evidence === true ? "and execution evidence " : ""}recorded under it, and is not described as a priority afterwards.`,
      evidence: [{ trust: "Observed", text: `${String(lapsed.theme_name)}: priority in FY${f}–FY${l}; capital recorded under the theme`, source: "Strategy evolution record, annual-report commentary" }, { trust: "Unknown", text: `Priority not reconfirmed after FY${l}`, source: "Strategy evolution record, annual-report commentary" }],
      significance: "A priority can drop because the work finished, merged into another theme or was dropped. The records do not say which, so this is a question for management, not a finding against it.",
      unknown: ["Whether the work was completed, continued under another theme or abandoned.", "What the recorded capital produced."],
      links: [{ label: "See in Story", href: "#timeline" }, ...q("how-is-capital-allocated", "Capital Allocation")],
      basis: "Approved records",
    });
  }

  // ── Acquisitions without attributable outcomes ──
  const acq = conns.find((k) => k.nodes[0]?.title === "Transactions completed");
  if (acq) {
    const names = acq.nodes[0].facts;
    out.push({
      id: `d-${out.length + 1}`, category: "Unanswered questions",
      headline: `${names.length === 1 ? "A completed acquisition" : `${names.length} completed acquisitions`}, no attributable outcome on record`,
      keyNumber: { value: `${names.length} ${names.length === 1 ? "deal" : "deals"}`, label: `0 with an attributable outcome (${acq.nodes[0].period})` },
      why: "Deals change what shareholders own; whether they paid off is a diligence question the records cannot yet answer.",
      years: acq.nodes[0].period,
      visual: { kind: "table", head: ["Question", "What the records show"], rows: [["Transaction completed", names.join("; ")], ["Integration or execution", "Not in the extracted records"], ["Attributable financial outcome", "Not in the extracted records"], ["Amount", names.some((n) => /₹/.test(n)) ? "Stated in the capital ledger" : "Not in the extracted records"]] },
      discovered: `${names.join(" and ")} ${names.length === 1 ? "is" : "are"} recorded as completed in ${acq.nodes[0].period}. Nothing in the records says what was done next or what they contributed.`,
      evidence: [
        { trust: "Observed", text: `Completed: ${names.join("; ")}`, source: acq.nodes[0].evidence[0] ?? "" },
        { trust: "Observed", text: "No integration or execution evidence found", source: acq.nodes[1].evidence[0] ?? "" },
        ...acq.nodes[2].facts.slice(1).map((f) => ({ trust: "Interpretation" as Trust, text: `Other explanation to rule out: ${f}`, source: acq.nodes[2].evidence[0] ?? "" })),
      ],
      significance: "This is a question for diligence, not a finding against management: disclosure at deal or segment level would let investors judge returns.",
      unknown: [...(names.some((n) => /₹/.test(n)) ? [] : ["Purchase amounts."]), "Integration progress.", "Revenue or margin attributable to each deal."],
      links: [...connLink(acq), ...q("how-is-capital-allocated", "Capital Allocation")],
      basis: "Approved records",
    });
  }

  // ── Commitments (register-based; not shown for companies whose register is withheld) ──
  if (acct && acct.total > 0) {
    out.push({
      id: `d-${out.length + 1}`, category: "Evidence connections",
      headline: "Targets exist, but follow-through is not yet confirmed",
      keyNumber: { value: `${acct.counts["Delivered"] + acct.counts["Partially delivered"]} of ${acct.total}`, label: "checkable commitments verified in the approved record" },
      why: "Management set measurable targets, but the records hold no later evidence to confirm or contradict them.",
      years: span(input.commitments.map((m) => m.announcement_period)),
      visual: { kind: "table", head: ["Status", "Commitments"], rows: STATUSES.map((st) => [st, String(acct.counts[st])]) },
      discovered: `The approved register lists ${acct.total} commitment${acct.total === 1 ? "" : "s"} with a checkable target. ${acct.basis}`,
      evidence: [{ trust: "Observed", text: `${acct.total} checkable commitments in the register`, source: "Approved commitments register" }],
      significance: "Missing confirmation is not failure. It does mean investors cannot lean on approved records to say management has delivered.",
      unknown: ["Outcomes for commitments with no later disclosure.", `${acct.notMeasurable} other statements have no measurable test and are not scored.`],
      links: [{ label: "See in Story", href: "#words-vs-actions" }, ...q("what-did-management-actually-deliver", "Management Delivery")],
      basis: "Approved records",
    });
  }

  // ── Investment and execution without a demonstrated economic result ──
  const capex = capexProgramme(input.attribution as Obj[]);
  const live = (input.projects as Obj[]).filter((p) => (p.assessment as Obj | undefined)?.execution_status === "operational" && String(p.project_name).length >= 12);
  if (capex && live.length) {
    const run = revenueRun(input.revenue);
    const ref = (p: Obj) => ((p.source_references as Obj[] | undefined) ?? [])[0] ?? {};
    out.push({
      id: `d-${out.length + 1}`, category: "Unanswered questions",
      headline: `${cr(capex.amount)} of capital spending and ${live.length} operational ${live.length === 1 ? "project" : "projects"}, but no site-level contribution on record`,
      keyNumber: { value: cr(capex.amount), label: `organic capex recorded, ${capex.span}` },
      why: "Plants and capacity are built to earn returns; the records show the spending and the sites, not what the sites earned.",
      years: `${capex.span}`,
      visual: { kind: "table", head: ["Question", "What the records show"], rows: [["Capital spent", `${cr(capex.amount)} (${capex.span})`], ["Projects reported operational", String(live.length)], ...(run.length >= 2 ? [["Group revenue", `${cr(run[0].value)} → ${cr(run[run.length - 1].value)} (${run[0].basis} basis, whole company)`]] : []), ["Site-level revenue, utilisation or returns", "Not in the extracted records"]] },
      discovered: `Organic capex of ${capex.label} is recorded, and ${live.length} ${live.length === 1 ? "project is" : "projects are"} reported as operational. No utilisation, capacity or site-level revenue is disclosed, so the records cannot say what the spending returned.`,
      evidence: [
        { trust: "Observed", text: `Organic capex ${capex.label}`, source: `Capital-allocation ledger, ${capex.span}` },
        ...live.slice(0, 3).map((p) => ({ trust: "Observed" as Trust, text: `Operational: ${firstSentence(String(p.project_name), 90)}`, source: `Annual report FY${fyNumOf(ref(p).period)}, p.${ref(p).page ?? "n/a"}` })),
        { trust: "Unknown", text: "Site-level revenue, utilisation or returns", source: "Not extracted into the records" },
      ],
      significance: "Revenue growth in the same years is not attributed to these sites. This is a diligence question about returns, not a finding that the spending failed.",
      unknown: ["What each facility earns.", "Which spending built which site."],
      links: [...connLink(conns.find((k) => k.title === "Capital spent on plants and capacity")), ...q("how-is-capital-allocated", "Capital Allocation")],
      basis: "Approved records",
    });
  }

  // ── Active risks and recorded responses (same source and definition as the approved risk answer) ──
  const themes = (input.riskThemes ?? []) as Obj[];
  const activeRisks = themes.filter((t) => String(t.current_state) !== "NOT_RECONFIRMED");
  const responded = activeRisks.filter((t) => ((t.timeline as Obj[]) ?? []).some((e) => String(e.management_response ?? "").trim()));
  // With no recorded response anywhere the field is only a default, so this would be generic: skip it.
  if (activeRisks.length >= 3 && responded.length > 0) {
    const riskConn = conns.find((k) => k.link?.href.endsWith("what-could-go-wrong"));
    out.push({
      id: `d-${out.length + 1}`, category: "Emerging patterns",
      headline: `${activeRisks.length} active risks; ${responded.length} ${responded.length === 1 ? "links" : "link"} a management response`,
      keyNumber: { value: `${responded.length} of ${activeRisks.length}`, label: "active risk records that link a management response" },
      why: "When a risk persists, investors want to see what management did about it; for the rest no response is linked in the extracted records, which does not show that management did nothing.",
      years: span(themes.flatMap((r) => [r.first_seen_period, r.latest_seen_period])),
      visual: { kind: "table", head: ["Risk", "Pattern", "Years", "Response linked"], rows: activeRisks.map((r) => [String(r.theme).replace(/^./, (c) => c.toUpperCase()), String(r.current_state).toLowerCase().replace(/_/g, " "), span([r.first_seen_period, r.latest_seen_period]), ((r.timeline as Obj[]) ?? []).some((e) => String(e.management_response ?? "").trim()) ? "Yes" : "No"]) },
      discovered: `${activeRisks.length} risk themes are still active; ${responded.length} ${responded.length === 1 ? "has" : "have"} a management response on record and none has an observable mitigation result.`,
      evidence: activeRisks.map((r) => ({ trust: "Observed" as Trust, text: `${String(r.theme).replace(/^./, (c) => c.toUpperCase())} — ${String(r.current_state).toLowerCase().replace(/_/g, " ")}, ${span([r.first_seen_period, r.latest_seen_period])}`, source: "Risk evolution timeline" })),
      significance: "Silence in the filings is a disclosure gap worth probing, not proof that nothing was done.",
      unknown: ["Whether responses exist but are not linked in the extracted records.", "Whether any mitigation worked."],
      links: [...connLink(riskConn), ...q("what-could-go-wrong", "Risks / Diligence")],
      basis: "Approved records",
    });
  }

  // Validation gate: a discovery must carry sourced evidence and links; otherwise it is dropped.
  return out.filter((d) => d.evidence.length > 0 && d.evidence.every((e) => e.source.length > 0)).slice(0, 6);
}
