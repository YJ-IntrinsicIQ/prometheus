// The Investment Panel: five specialist perspectives over ONE evidence base (approved answers + canonical records).
// Everything here is deterministic presentation logic. Each observation states a stored fact or a plain calculation
// from stored figures, and says which; each framework-specific reading is a fixed, hedged sentence. Nothing is rated,
// no valuation is estimated, and a lens without evidence is listed as missing, never filled in.
import { companyRoute, questionRoute } from "@/src/lib/routes";
import { plain, QUESTIONS } from "@/src/lib/story/question-view";
import type { Story, StoryInputs } from "@/src/lib/story/story-adapter";
import { cr, fyNum } from "@/src/lib/story/text";
import type { Catalog } from "@/src/lib/catalog/catalog";
import type { PanelData, Pt } from "./data";
import { SPECIALISTS, type ProposedQuestion, type SpecialistId } from "./specialists";

type Obj = Record<string, unknown>;
export type Basis = "Reported" | "Calculated" | "Approved answer" | "Interpretation";
export type Obs = { text: string; basis: Basis; sources: string[]; link?: { label: string; href: string }; tag?: string };
export type Gap = { text: string; kind: "Missing data" | "Missing measurement" | "Untested assumption"; question?: string };
export type Investigate = { id: string; title: string; why: string; status: "approved" | "not-approved"; href: string; preview?: string };
export type SpecialistView = {
  id: SpecialistId; name: string; framework: string; coreQuestion: string; investorQuestion: string; evaluates: string[];
  lenses: { name: string; available: boolean }[];
  observations: Obs[]; questions: Investigate[]; proposed: ProposedQuestion[]; uncertain: Gap[];
  takeaway: string; openQuestion: string;
};
export type Panel = { slug: string; company: string; available: string[]; docs: string[]; titles?: Record<string, string>; specialists: SpecialistView[] };

export type PanelInputs = {
  slug: string;
  company: string;
  data: PanelData;
  story: Story;
  inputs: StoryInputs;
  answers: Record<string, Obj>;
  catalog: Catalog; // the canonical question catalog: titles and the certified ids that serve each question
  notices: { title: string; text: string }[]; // data-integrity notes carried by the approved question pages
};

// ── formatting ──
const r1 = (n: number) => Math.round(n * 10) / 10;
const pc = (n: number) => `${r1(n)}%`;
const x = (n: number) => `${(Math.round(n * 100) / 100).toFixed(2)}×`;
const span = (pts: Pt[]) => `FY${pts[0].fy}–FY${pts[pts.length - 1].fy}`;
const cagr = (pts: Pt[]) => (pts.length >= 2 && pts[0].v > 0 && pts[pts.length - 1].v > 0 ? (Math.pow(pts[pts.length - 1].v / pts[0].v, 1 / (pts[pts.length - 1].fy - pts[0].fy)) - 1) * 100 : null);
const basisWord = (b: string) => (b === "unknown" ? "reporting basis not yet identified in the extracted records" : b);
const fin = (fy: number, what = "Financial statements") => `${what} FY${fy}`;
const titleOf = (id: string, catalog: Catalog) => QUESTIONS.find((q) => q.id === id)?.title ?? catalog.questions.find((q) => q.id === id)?.title ?? id.replace(/-/g, " ").replace(/^./, (c) => c.toUpperCase());
const leadOf = (text: string, max = 260) => {
  const out: string[] = [];
  for (const s of plain(text).split(/(?<=[a-z0-9)%”™]\.)\s+(?=[A-Z(])/)) { if (out.join(" ").length + s.length > max && out.length) break; out.push(s); }
  return out.join(" ");
};

type Ctx = PanelInputs & { bank: boolean; ansLead: (q: string, max?: number) => string | null; ansSrc: (q: string) => string; ansLink: (q: string, label?: string) => Obs["link"] };
type Built = { lenses: { name: string; available: boolean }[]; observations: Obs[]; uncertain: Gap[]; takeaway: string };

const GAP_VALUATION: Gap = { kind: "Missing data", text: "No market price, price history or valuation estimate is in the records. Prometheus holds no external market data, so intrinsic value, margin of safety and any price-based ratio cannot be computed.", question: "What price would give a margin of safety? (needs a market price the records do not hold)" };

// ── Graham: valuation & margin of safety ──
function graham(c: Ctx): Built {
  const { data: d } = c;
  const obs: Obs[] = [], gaps: Gap[] = [];
  const nw = d.latest("balance_sheet_strength", "net_worth"), cash = d.latest("balance_sheet_strength", "cash_and_equivalents");
  const debt = c.bank ? null : d.latest("debt_and_liquidity", "total_debt"), de = c.bank ? null : d.latest("debt_and_liquidity", "debt_to_equity");
  const nd = c.bank ? null : d.latest("debt_and_liquidity", "net_debt"), ta = d.latest("balance_sheet_strength", "total_assets");
  const netCash = nd && nd.v < 0 && ta && Math.abs(nd.v) <= ta.v ? Math.abs(nd.v) : null;
  const bsOk = !!nw;
  // Each figure carries its own year: a balance from a different year than the sentence's FY must say so, never inherit it.
  const yr = (p: { fy: number } | null) => (nw && p && p.fy !== nw.fy ? ` (as of FY${p.fy})` : "");
  if (nw) {
    obs.push({ basis: "Reported", sources: [fin(nw.fy, "Financial statements"), "Balance-sheet records"], text: `FY${nw.fy}: net worth ${cr(nw.v)}${debt ? `; total debt ${cr(debt.v)}${yr(debt)}${de ? ` (debt-to-equity ${de.v.toFixed(2)})` : ""}` : ""}${cash ? `; ${cash.defn === "cash_and_bank_balances" ? "cash and bank balances" : "cash and equivalents"} ${cr(cash.v)}${yr(cash)}` : ""}${netCash ? `; net cash ${cr(netCash)}${nd?.defn === "cash_and_bank_balances" ? " (cash and bank balances less total debt)" : ""}${yr(nd)}` : ""}${nw.basis === "unknown" ? " (reporting basis not yet identified in the extracted records)" : ""}.` });
    if (de) obs.push({ basis: "Interpretation", sources: [fin(de.fy)], text: de.v <= 0.5 ? "Borrowing is small relative to equity — the kind of balance-sheet resilience Graham looked for. It says nothing about the price paid." : "Borrowing is material relative to equity; Graham's downside test would need the debt's cost, maturity and cover examined." });
  }
  if (c.bank) {
    const car = d.latest("banking_measures", "capital_adequacy_ratio"), gnpa = d.latest("banking_measures", "gross_npa_ratio"), nnpa = d.latest("banking_measures", "net_npa_ratio");
    const income = d.latest("revenue_and_income", "total_income"), nim = d.latest("banking_measures", "net_interest_margin");
    const nii = d.latest("revenue_and_income", "net_interest_income"), deposits = d.latest("banking_measures", "total_deposits"), branches = d.latest("banking_measures", "branch_network");
    if (car || gnpa || nnpa) obs.push({basis:"Reported",sources:["Filing management highlights; rounded ratios may differ from audited schedules"],text:`Bank-reported measures: ${[car ? `capital adequacy ${pc(car.v)} in FY${car.fy}` : null, gnpa ? `gross NPA ${pc(gnpa.v)} in FY${gnpa.fy}` : null, nnpa ? `net NPA ${pc(nnpa.v)} in FY${nnpa.fy}` : null].filter(Boolean).join("; ")}. Deposits fund the bank; industrial borrowing ratios do not apply.`});
    else gaps.push({kind:"Missing measurement",text:"Bank capital adequacy and asset-quality measures have not been extracted; industrial borrowing ratios do not apply."});
    if (nii || nim || income || deposits || branches) obs.push({basis:"Reported",sources:["Filing management highlights; definitions retained"],text:`Bank operating scale: ${[nii ? `net interest income ${cr(nii.v)} in FY${nii.fy}` : null, nim ? `net interest margin ${pc(nim.v)} in FY${nim.fy}` : null, income ? `total income ${cr(income.v)} in FY${income.fy}` : null, deposits ? `total deposits ${cr(deposits.v)} in FY${deposits.fy}` : null, branches ? `${Math.round(branches.v)} branches in FY${branches.fy}` : null].filter(Boolean).join("; ")}. These establish scale, not management skill or future credit quality.`});
  }
  const pat = d.run("revenue_and_income", "pat");
  let allPositive = false;
  if (pat.length >= 3) {
    const drops = pat.slice(1).map((p, i) => ({ fy: p.fy, g: ((p.v - pat[i].v) / Math.abs(pat[i].v)) * 100 })).filter((q) => q.g < 0).sort((a, b) => a.g - b.g);
    allPositive = pat.every((p) => p.v > 0);
    obs.push({ basis: "Calculated", sources: [fin(pat[pat.length - 1].fy), "Financial statements, multi-year"], text: `Profit after tax was ${allPositive ? "positive in all" : `positive in ${pat.filter((p) => p.v > 0).length} of`} ${pat.length} reported years (${span(pat)}, ${basisWord(pat[0].basis)} basis), from ${cr(pat[0].v)} to ${cr(pat[pat.length - 1].v)}; ${drops.length ? `the largest year-on-year decline was ${pc(Math.abs(drops[0].g))} (FY${drops[0].fy})` : "there was no year-on-year decline"}.` });
  } else {
    const p = d.latest("revenue_and_income", "pat");
    if (p) obs.push({ basis: "Reported", sources: [fin(p.fy)], text: `FY${p.fy} profit after tax was ${cr(p.v)} (${basisWord(p.basis)}).` });
    gaps.push({ kind: "Missing data", text: "Earnings cannot be compared across years like for like: fewer than three consecutive years are reported on one stated basis.", question: "How stable were earnings across years? (needs a consistent multi-year series)" });
  }
  if (c.bank) {
    gaps.push({ kind: "Missing measurement", text: "Cash-conversion and working-capital measures are marked not economically meaningful for this company in the records (banking schedule)." });
  } else {
    const cc = d.run("cash_conversion", "cfo_to_pat");
    const cl = cc.length >= 2 ? cc : (() => { const l = d.latest("cash_conversion", "cfo_to_pat"); return l ? [l] : []; })();
    if (cl.length) {
      const last = cl[cl.length - 1], low = [...cl].sort((a, b) => a.v - b.v)[0];
      obs.push({ basis: "Calculated", sources: [fin(last.fy), "Operating cash flow and profit"], text: cl.length >= 2 ? `Operating cash flow was ${x(last.v)} profit in FY${last.fy}; over ${span(cl)} it ranged from ${x(low.v)} (FY${low.fy}) to ${x([...cl].sort((a, b) => b.v - a.v)[0].v)} (FY${[...cl].sort((a, b) => b.v - a.v)[0].fy}).` : `Operating cash flow was ${x(last.v)} profit in FY${last.fy} (${basisWord(last.basis)}); a multi-year pattern cannot be shown.` });
    }
  }
  const row = c.data.roi[c.data.roi.length - 1], payout = d.latest("per_share", "payout_ratio");
  if (row && typeof row.dividends === "number") obs.push({ basis: "Reported", sources: [fin(fyNum(String(row.fiscal_year)) ?? 0, "Capital-allocation ledger")], text: `Dividends paid were ${cr(Math.abs(row.dividends as number))} in FY${fyNum(String(row.fiscal_year))}${payout ? ` (payout ${pc(payout.v)} of profit)` : ""}.` });
  const ps = [...d.perShare].reverse().find((p) => typeof p.eps_basic === "number");
  if (ps) obs.push({ basis: "Reported", sources: [fin(fyNum(String(ps.fiscal_year)) ?? 0, "Per-share records")], text: `Per-share inputs exist for a future price comparison — EPS ₹${ps.eps_basic}${typeof ps.owner_earnings_per_share === "number" ? `; estimated owner earnings per share ₹${r1(ps.owner_earnings_per_share as number)}` : ""}${typeof ps.book_value_per_share === "number" ? `; book value per share ₹${r1(ps.book_value_per_share as number)}` : ""} (FY${fyNum(String(ps.fiscal_year))}). No price is available to compare them with.` });
  gaps.push(GAP_VALUATION);
  if (!d.latest("debt_and_liquidity", "interest_coverage") && !c.bank) gaps.push({ kind: "Missing measurement", text: "Interest coverage is not extracted into the records, so the burden of debt on earnings cannot be tested from them." });
  if (!d.latest("per_share", "book_value_per_share") && !ps?.book_value_per_share) gaps.push({ kind: "Missing measurement", text: "Book value per share is not extracted into the records, so an asset-based floor value cannot be built from them." });
  const contingent = d.latest("balance_sheet_strength", "contingent_liabilities");
  if (contingent) obs.push({basis:"Reported",sources:[fin(contingent.fy,"Contingent-liability note")],text:`Disclosed contingent liabilities: ${cr(contingent.v)} in FY${contingent.fy}. These are claims not acknowledged as debt, not borrowings or certain cash outflows.`});
  else gaps.push({ kind: "Untested assumption", text: "Contingent liabilities and off-balance-sheet obligations have not been extracted, so downside protection is judged on reported figures only." });
  const lenses = [{ name: "Balance-sheet strength", available: bsOk }, { name: "Earnings stability", available: pat.length >= 3 }, { name: "Cash behind earnings", available: obs.some((o) => /cash flow/.test(o.text)) }, { name: "Dividend record", available: !!row && typeof row.dividends === "number" }, { name: "Per-share inputs", available: !!ps }, { name: "Market price and valuation", available: false }];
  const sound = !c.bank && de !== null && de.v <= 0.5 && allPositive;
  const takeaway = sound
    ? "The financial-strength half of Graham's test looks sound on the stored figures: low borrowing relative to equity and positive profit in every reported year. The other half — whether the price is substantially below conservative worth — cannot be assessed, because the records hold no market price or valuation estimate. No margin of safety is stated."
    : `Only part of Graham's test can be checked from the records (${lenses.filter((l) => l.available).map((l) => l.name.toLowerCase()).join(", ") || "none of its lenses"}). The valuation half cannot, because no market price or valuation estimate is available. No margin of safety is stated.`;
  return { lenses, observations: obs, uncertain: gaps, takeaway };
}

// ── Fisher: business quality & growth ──
function fisher(c: Ctx): Built {
  const { data: d, story } = c;
  const obs: Obs[] = [], gaps: Gap[] = [];
  const rev = d.run("revenue_and_income", "revenue"), pat = d.run("revenue_and_income", "pat");
  if (rev.length >= 3) {
    const g = cagr(rev), gp = cagr(pat);
    obs.push({ basis: "Calculated", sources: [fin(rev[rev.length - 1].fy), "Financial statements, multi-year"], text: `Revenue grew from ${cr(rev[0].v)} (FY${rev[0].fy}) to ${cr(rev[rev.length - 1].v)} (FY${rev[rev.length - 1].fy}), about ${pc(g ?? 0)} a year on a ${basisWord(rev[0].basis)} basis${pat.length >= 3 && gp !== null ? `; profit grew about ${pc(gp)} a year` : ""}.` });
  } else gaps.push({ kind: "Missing data", text: "A multi-year growth record cannot be shown: fewer than three consecutive years are reported on one stated basis.", question: "How fast has the business grown, like for like? (needs a consistent multi-year series)" });
  const drivers = c.data.model.engines.filter((e) => e.growth !== null).sort((a, b) => (b.growth ?? 0) - (a.growth ?? 0));
  if (drivers.length) obs.push({ basis: "Reported", sources: [`Company model: revenue by geography ${drivers[0].period.toUpperCase()}`], text: `Growth in ${drivers[0].period.toUpperCase()} by region: ${drivers.map((e) => `${e.name} ${(e.growth ?? 0) >= 0 ? "+" : ""}${pc((e.growth ?? 0) * 100)}`).join(", ")}.` });
  else gaps.push({ kind: "Missing data", text: "Growth cannot be broken down by product, segment or region: the records hold no revenue breakdown for this company.", question: "Which products or segments drive growth? (needs a segment revenue history)" });
  const theme = c.inputs.strategyThemes.find((t) => /innovation|r&d|research/i.test(String(t.theme_name)));
  if (theme) obs.push({ basis: "Reported", sources: ["Strategy evolution record, annual-report commentary"], text: `${String(theme.theme_name)} is recorded as a management priority from FY${fyNum(String(theme.first_period))}${theme.current_status === "CURRENT_PRIORITY" ? " and is still current" : `, last confirmed in FY${fyNum(String(theme.last_confirmed_period))}`}; ${theme.capital_backed === true || theme.capital_backed === "True" ? "capital is recorded under it." : "no capital is recorded under it."}` });
  if (c.bank) gaps.push({ kind: "Missing measurement", text: "Research and development spending and pipeline outcomes do not apply to a bank, so R&D productivity is not a test of this business." });
  else gaps.push({ kind: "Missing measurement", text: "Research and development spending, pipeline stages and pipeline outcomes are not in the structured records, so R&D productivity cannot be judged.", question: "How productive is R&D spending? (needs R&D expense and pipeline outcomes)" });
  const rows = story.commitments?.filter((r) => r.hard) ?? [];
  if (rows.length) {
    const n = (k: string) => rows.filter((r) => r.deliveryClass === k).length;
    obs.push({ basis: "Approved answer", sources: [c.ansSrc("what-did-management-actually-deliver"), ...rows.flatMap((r) => r.evidence).slice(0, 3)], link: c.ansLink("what-did-management-actually-deliver", "Management Delivery"), text: `Of ${rows.length} hard commitments (specific target and deadline), the reports show progress on ${rows.filter((r) => r.hasEvidence).length}: ${n("reached")} target level reported reached, ${n("partly")} partly evidenced, ${n("in_progress")} in progress. The commitment tracker still shows none verified, and none has a confirmed economic outcome.` });
  } else if (story.accountability?.total) obs.push({ basis: "Approved answer", sources: [c.ansSrc("what-has-management-promised")], link: c.ansLink("what-has-management-promised", "Management Promises"), text: `${story.accountability.total} specific commitments are tracked; the records neither confirm delivery nor contradict any of them (unable to verify) — unresolved, not failed.` });
  const mq = c.ansLead("how-good-is-management");
  if (mq) obs.push({ basis: "Approved answer", sources: [c.ansSrc("how-good-is-management")], link: c.ansLink("how-good-is-management", "Management Intelligence"), text: mq });
  const capex = d.run("cash_conversion", "capex"), cfo = d.run("cash_conversion", "cfo");
  if (capex.length >= 2) {
    const a = capex[capex.length - 1], b = capex[capex.length - 2], cf = cfo.find((p) => p.fy === a.fy);
    obs.push({ basis: "Calculated", sources: [fin(a.fy, "Cash-flow statement")], text: `Capital spending was ${cr(Math.abs(a.v))} in FY${a.fy} versus ${cr(Math.abs(b.v))} in FY${b.fy} (${Math.abs(a.v) >= Math.abs(b.v) ? "up" : "down"} ${pc(Math.abs((Math.abs(a.v) - Math.abs(b.v)) / Math.abs(b.v)) * 100)})${cf && !c.bank ? `, ${pc((Math.abs(a.v) / cf.v) * 100)} of operating cash flow` : ""}.` });
  }
  gaps.push({ kind: "Missing data", text: "Competitive position — market share, pricing power against peers — is not in the records, so durability of growth against competition cannot be tested." });
  gaps.push({ kind: "Untested assumption", text: "Management depth, succession and the quality of its sales and research organisations are not in the structured records; the approved management answer covers consistency of statements, not people." });
  const lenses = [{ name: "Growth record", available: rev.length >= 3 }, { name: "Growth drivers", available: drivers.length > 0 }, { name: "Innovation and R&D", available: !!theme }, { name: "Execution against plans", available: rows.length > 0 || !!story.accountability?.total }, { name: "Management candour", available: !!mq }, { name: "Reinvestment", available: capex.length >= 2 }];
  const takeaway = `${lenses.filter((l) => l.available).length} of ${lenses.length} Fisher lenses have some evidence here. ${rev.length >= 3 ? "The growth record is documented, " : "A like-for-like growth record cannot be shown, "}but whether growth is durable turns on R&D productivity and competitive position, and the records contain neither. ${rows.length ? "Management has disclosed progress on its hard commitments, though none is yet tied to an economic result." : "Management's commitments are tracked but not yet confirmed either way."} This is a framework to apply, not a score.`;
  return { lenses, observations: obs, uncertain: gaps, takeaway };
}

// ── Buffett: business economics & capital allocation ──
function buffett(c: Ctx): Built {
  const { data: d, story } = c;
  const obs: Obs[] = [], gaps: Gap[] = [];
  const roe = d.run("return_on_capital", "roe"), npm = d.run("margins", "npm");
  const roeL = roe.length ? roe : (() => { const l = d.latest("return_on_capital", "roe"); return l ? [l] : []; })();
  if (roeL.length) {
    const a = roeL[roeL.length - 1];
    obs.push({ basis: "Reported", sources: [fin(a.fy, "Financial statements")], text: `Return on equity was ${pc(a.v)} in FY${a.fy}${roeL.length >= 2 ? ` (between ${pc(Math.min(...roeL.map((p) => p.v)))} and ${pc(Math.max(...roeL.map((p) => p.v)))} over ${span(roeL)})` : ` (${basisWord(a.basis)}; a multi-year pattern cannot be shown)`}${npm.length >= 2 ? `; net margin ${pc(npm[npm.length - 1].v)}` : ""}.` });
  }
  if (!d.latest("return_on_capital", "roce")) gaps.push(c.bank ? { kind: "Missing measurement", text: "Return on capital employed does not apply to a bank, whose funding is deposits; returns are judged on assets and equity.", question: "What return does incremental capital earn? (needs return on assets and equity)" } : { kind: "Missing measurement", text: "Return on capital employed is not extracted into the records, so returns on all capital (debt and equity) cannot be assessed from them.", question: "What return does incremental capital earn? (needs return on capital employed)" });
  const oe = [...d.ownerEarnings].reverse().find((b) => typeof b.reported_pat === "number");
  if (oe && !c.bank) {
    const fy = fyNum(String(oe.fiscal_year)) ?? 0, est = oe.owner_earnings_estimate as number | null, cf = oe.cfo as number | null, rp = oe.reported_pat as number;
    obs.push({ basis: "Calculated", sources: [fin(fy, "Owner-earnings bridge"), "Cash-flow statement"], text: `FY${fy}, three different measures — reported profit ${cr(rp)}; operating cash flow ${cf !== null ? cr(cf) : "not available"}; estimated owner earnings ${est !== null ? `${cr(est)} (${pc((est / rp) * 100)} of reported profit)` : "not available"}. The estimate deducts all identified capital spending from operating cash flow because the maintenance-versus-growth split is not disclosed.` });
    if (String(oe.maintenance_growth_split_status) === "missing") gaps.push({ kind: "Missing measurement", text: "The maintenance versus growth capex split is not in the extracted records, so owner earnings are an estimate of limited precision.", question: "How much of earnings can owners take out? (needs the maintenance capex split)" });
  } else if (c.bank) gaps.push({ kind: "Missing measurement", text: "Owner earnings are not computed for a bank: operating cash flow includes changes in loans and deposits and does not describe distributable cash." });
  const cc = d.run("cash_conversion", "cfo_to_pat");
  if (cc.length >= 3 && !c.bank) {
    const lo = [...cc].sort((a, b) => a.v - b.v)[0], hi = [...cc].sort((a, b) => b.v - a.v)[0];
    obs.push({ basis: "Calculated", sources: [fin(cc[cc.length - 1].fy), "Operating cash flow and profit"], text: `Operating cash flow ranged from ${x(lo.v)} (FY${lo.fy}) to ${x(hi.v)} (FY${hi.fy}) of profit over ${span(cc)}${lo.v < 0.8 ? ` — cash generation was ${lo.fy === cc[cc.length - 1].fy ? "weakest in the latest year" : `weak in FY${lo.fy} and recovered`}` : ""}.` });
  }
  const cap = c.ansLead("how-is-capital-allocated", 300);
  const row = c.data.roi[c.data.roi.length - 1];
  if (row && typeof row.capex_deployed === "number") obs.push({ basis: "Reported", sources: [fin(fyNum(String(row.fiscal_year)) ?? 0, "Capital-allocation ledger")], link: c.ansLink("how-is-capital-allocated", "Capital Allocation"), text: `FY${fyNum(String(row.fiscal_year))} uses of cash recorded: capital spending ${cr(Math.abs(row.capex_deployed as number))}${typeof row.dividends === "number" ? `, dividends ${cr(Math.abs(row.dividends as number))}` : ""}${typeof row.buybacks === "number" ? `, buybacks ${cr(Math.abs(row.buybacks as number))}` : ""}${typeof row.debt_repayment === "number" ? `, debt repayment ${cr(Math.abs(row.debt_repayment as number))}` : ""}.` });
  if (cap) obs.push({ basis: "Approved answer", sources: [c.ansSrc("how-is-capital-allocated")], link: c.ansLink("how-is-capital-allocated", "Capital Allocation"), text: cap });
  const outcome = story.discoveries.filter((dd) => /no attributable outcome|site-level contribution/.test(dd.headline));
  if (outcome.length) obs.push({ basis: "Interpretation", sources: outcome.flatMap((o) => o.evidence.slice(0, 1).map((e) => e.source)), link: { label: "Discoveries", href: `${companyRoute(c.slug)}#discoveries` }, text: `${outcome.map((o) => o.headline.replace(/^./, (ch) => ch.toLowerCase())).join("; ")}. Capital is being deployed; the records cannot say what it has earned, so allocation quality is unproven rather than poor.` });
  const rows = story.commitments?.filter((r) => r.hard) ?? [];
  if (rows.length) obs.push({ basis: "Approved answer", sources: [c.ansSrc("what-did-management-actually-deliver")], link: c.ansLink("what-did-management-actually-deliver", "Management Delivery"), text: `Management's statements are not contradicted by the reports: ${rows.filter((r) => r.hasEvidence).length} of ${rows.length} hard commitments show reported progress. None has yet produced a confirmed economic result, and the commitment tracker (unable to verify for all) has not been updated to reflect the progress.` });
  else { const del = c.ansLead("what-did-management-actually-deliver"); if (del) obs.push({ basis: "Approved answer", sources: [c.ansSrc("what-did-management-actually-deliver")], link: c.ansLink("what-did-management-actually-deliver", "Management Delivery"), text: del }); }
  const lo = npm.length ? Math.min(...npm.map((p) => p.v)) : 0, hi = npm.length ? Math.max(...npm.map((p) => p.v)) : 0;
  const stable = npm.length >= 4 && hi - lo <= 6;
  if (npm.length >= 4) obs.push({ basis: "Interpretation", sources: [fin(npm[npm.length - 1].fy)], text: stable ? `Net margin stayed between ${pc(lo)} and ${pc(hi)} over ${span(npm)}. Stable margins and returns are consistent with a durable franchise but are not proof of a moat.` : `Net margin ranged from ${pc(lo)} to ${pc(hi)} over ${span(npm)}, so margin stability — one indicator of a durable franchise — is not shown; no inference about a moat is drawn.` });
  gaps.push({ kind: "Missing data", text: "No moat evidence — pricing power, market share or switching costs against peers — is in the records.", question: "Does the business have a durable moat? (needs peer and pricing evidence)" });
  gaps.push({ kind: "Untested assumption", text: "Whether this is within your circle of competence is a judgement the records cannot make; they describe the business but do not test your understanding of it." });
  gaps.push({ kind: "Missing data", text: "Management incentives (pay, ESOP terms, promoter alignment) are not in the structured records." });
  const lenses = [{ name: "Returns on capital", available: roeL.length > 0 }, { name: "Earnings, owner earnings and cash", available: !!oe && !c.bank }, { name: "Cash durability", available: cc.length >= 3 && !c.bank }, { name: "Capital allocation", available: !!cap || !!row }, { name: "Management trust", available: rows.length > 0 || !!c.ansLead("what-did-management-actually-deliver") }, { name: "Moat indicators", available: stable }];
  const takeaway = `${lenses.filter((l) => l.available).length} of ${lenses.length} Buffett lenses have some evidence. ${roeL.length ? `Returns and margins are documented${stable ? " and stable" : ""}, ` : "Returns are not documented, "}and cash generation ${oe && !c.bank ? "can be set against reported profit" : "cannot be set against reported profit with confidence"}. What the records cannot show is whether capital deployed has earned its keep: ${outcome.length ? "the acquisitions and capacity spending are recorded without attributable outcomes" : "outcomes of recorded investments are not established"}. A ten-year ownership view would need a moat assessment and an owner-earnings estimate with a disclosed maintenance split.`;
  return { lenses, observations: obs, uncertain: gaps, takeaway };
}

// ── Munger: risks & inversion ──
function munger(c: Ctx): Built {
  const { data: d, story, inputs } = c;
  const obs: Obs[] = [], gaps: Gap[] = [];
  const themes = inputs.riskThemes;
  const active = themes.filter((t) => String(t.current_state) !== "NOT_RECONFIRMED");
  const worsening = active.filter((t) => String(t.current_state) === "WORSENING").map((t) => String(t.theme));
  const responded = active.filter((t) => ((t.timeline as Obj[] | undefined) ?? []).some((e) => String(e.management_response ?? "").trim())).length;
  if (active.length) obs.push({ basis: "Reported", sources: ["Risk evolution timeline", c.ansSrc("what-could-go-wrong")], link: c.ansLink("what-could-go-wrong", "Risks / Diligence"), tag: `${active.length} active risk themes`, text: `${active.length} risk themes are active${worsening.length ? `; worsening: ${worsening.slice(0, 3).join(", ")}` : ""}; ${responded === 0 ? "no management response is linked to these risk records (the annual report may still describe a risk-management framework; the link is not extracted)" : `${responded} ${responded === 1 ? "links" : "link"} a management response; the others are not linked in the extracted records, which does not show that no response exists`}.` });
  const wc = c.data.workingCapital.rows[c.data.workingCapital.rows.length - 1];
  const wcOk = c.data.workingCapital.applicability === "applicable" && wc;
  if (wcOk && ["watch", "severe", "elevated"].includes(String(wc!.working_capital_intensity_status)) || (wcOk && ["watch", "elevated"].includes(String(wc!.cash_strain_risk)))) {
    const g = wc!.receivables_growth_vs_revenue_growth as number | null;
    obs.push({ basis: "Calculated", tag: "working-capital strain", sources: [fin(fyNum(String(wc!.fiscal_year)) ?? 0, "Working-capital records")], text: `Working capital is flagged "${String(wc!.working_capital_intensity_status)}" (cash strain "${String(wc!.cash_strain_risk)}") in FY${fyNum(String(wc!.fiscal_year))}: receivables ${typeof wc!.receivables === "number" ? cr(wc!.receivables as number) : "n/a"}${typeof wc!.receivable_days === "number" ? ` (${Math.round(wc!.receivable_days as number)} days)` : ""}${typeof wc!.cash_conversion_cycle === "number" ? `, cash conversion cycle ${Math.round(wc!.cash_conversion_cycle as number)} days` : ""}${g !== null && g !== undefined ? `; receivables grew ${r1(g)} percentage points faster than revenue` : ""}.` });
  }
  const cc = d.run("cash_conversion", "cfo_to_pat");
  const dip = cc.filter((p) => p.v < 0.8);
  if (dip.length && !c.bank) obs.push({ basis: "Calculated", tag: "a cash-conversion shortfall", sources: [fin(dip[0].fy, "Operating cash flow and profit")], text: `Cash conversion fell below 0.8× profit in ${dip.map((p) => `FY${p.fy} (${x(p.v)})`).join(", ")}: profit was not matched by cash in ${dip.length === 1 ? "that year" : "those years"}.` });
  const revAll = d.series("revenue_and_income", "revenue");
  const unknown = revAll.filter((p) => p.basis === "unknown").length;
  if (unknown) obs.push({ basis: "Calculated", tag: "unstated reporting basis", sources: ["Financial statements, multi-year"], text: `The reporting basis (consolidated or standalone) is not identified in the extracted records for ${unknown} of ${revAll.length} years of revenue, so year-on-year comparisons across them are withheld rather than assumed comparable.` });
  const ps = [...d.perShare].reverse()[0];
  if (ps && /warning/.test(String(ps.dilution_status))) obs.push({ basis: "Reported", tag: "per-share dilution", sources: [fin(fyNum(String(ps.fiscal_year)) ?? 0, "Per-share records")], text: `Per-share records carry a dilution warning for FY${fyNum(String(ps.fiscal_year))}: ${String(ps.qip_or_equity_issuance_effect)}.` });
  const rows = story.commitments?.filter((r) => r.hard) ?? [];
  if (rows.length && rows.every((r) => /unable to verify/i.test(r.states.tracker)) && rows.some((r) => r.hasEvidence)) obs.push({ basis: "Approved answer", tag: "a commitment tracker that no longer matches the reports", sources: [c.ansSrc("what-has-management-promised"), c.ansSrc("what-did-management-actually-deliver")], link: c.ansLink("what-did-management-actually-deliver", "Management Delivery"), text: `Tracker versus evidence: the commitment tracker records all ${rows.length} hard commitments as unable to verify, while the annual reports show progress on ${rows.filter((r) => r.hasEvidence).length}. That is a stale tracker, not a management contradiction — but no commitment has a confirmed economic outcome, and one reported figure (FY26 emissions reduction) fell.` });
  for (const n of c.notices) obs.push({ basis: "Approved answer", tag: "a data-integrity note on the approved answers", sources: ["Approved answer, data-integrity note"], text: `${n.title}. ${n.text}` });
  const op = story.discoveries.filter((dd) => /no attributable outcome|site-level contribution|dropped out/.test(dd.headline));
  if (op.length) obs.push({ basis: "Interpretation", tag: "capital deployed without attributable outcomes", sources: op.flatMap((o) => o.evidence.slice(0, 1).map((e) => e.source)), link: { label: "Discoveries", href: `${companyRoute(c.slug)}#discoveries` }, text: `Open questions raised by the records: ${op.map((o) => o.headline.replace(/^./, (ch) => ch.toLowerCase())).join("; ")}. These are things to ask, not findings against management.` });
  const big = c.data.model.engines.filter((e) => e.share !== null).sort((a, b) => (b.share ?? 0) - (a.share ?? 0));
  if (big.length >= 2) { const slow = [...big].filter((e) => e.growth !== null).sort((a, b) => (a.growth ?? 0) - (b.growth ?? 0))[0]; const top = big[0]; obs.push({ basis: "Reported", tag: "dependence on one region for growth", sources: [`Company model: revenue by geography ${top.period.toUpperCase()}`], text: `${top.name} is ${pc((top.share ?? 0) * 100)} of revenue and ${top.growth !== null ? `grew ${pc((top.growth ?? 0) * 100)}` : "growth is not shown"} in ${top.period.toUpperCase()}${slow && slow.name !== top.name ? `; ${slow.name} grew the slowest at ${pc((slow.growth ?? 0) * 100)}` : ""}. A thesis that assumes continued growth here depends on that region.` }); }
  gaps.push({ kind: "Missing data", text: "Management incentives (pay, ESOP terms, promoter alignment) are not in the structured records, so incentive-driven distortions cannot be tested.", question: "What do management incentives reward? (needs remuneration terms)" });
  gaps.push({ kind: "Missing data", text: "Competitive threats are not measured: there is no peer or market-share evidence, so only the company's own disclosed risks appear above." });
  gaps.push({ kind: "Untested assumption", text: "The absence of a warning on a lens is not a clean bill of health where that lens has no evidence; each missing lens below is an unexamined risk, not a cleared one.", question: "Which assumptions is the thesis resting on? (derive from the other specialists' open questions)" });
  const lenses = [{ name: "Disclosed risks", available: active.length > 0 }, { name: "Cash and working capital", available: !!wcOk || (cc.length >= 2 && !c.bank) }, { name: "Reporting and per-share warnings", available: unknown > 0 || !!(ps && /warning/.test(String(ps.dilution_status))) }, { name: "Tracker versus evidence", available: rows.length > 0 || c.notices.length > 0 }, { name: "Capital without outcomes", available: op.length > 0 }, { name: "Concentration", available: big.length >= 2 }];
  const top = obs.filter((o) => o.tag).slice(0, 4).map((o) => o.tag!);
  const takeaway = `Inverting the thesis, the evidence-supported ways it could fail are: ${top.join("; ") || "none yet evidenced"}. They are diligence questions drawn from the company's own records; none is a finding of wrongdoing. ${lenses.filter((l) => !l.available).length ? `${lenses.filter((l) => !l.available).map((l) => l.name.toLowerCase()).join(", ")} ${lenses.filter((l) => !l.available).length === 1 ? "has" : "have"} no evidence, which means unexamined, not safe.` : ""}`;
  return { lenses, observations: obs, uncertain: gaps, takeaway };
}

// ── Lynch: simplicity & growth opportunities ──
function lynch(c: Ctx): Built {
  const { data: d, story, inputs } = c;
  const obs: Obs[] = [], gaps: Gap[] = [];
  const what = d.model.what.replace(/\s+/g, " ").trim();
  if (what) obs.push({ basis: "Reported", sources: ["Company model (business model summary)"], link: { label: "Story", href: companyRoute(c.slug) }, text: what.length > 300 ? `${what.slice(0, 299).replace(/\s+\S*$/, "")}…` : what });
  const eng = d.model.engines.filter((e) => e.share !== null);
  if (eng.length) obs.push({ basis: "Reported", sources: [`Company model: revenue by geography ${eng[0].period.toUpperCase()}`], text: `Revenue by region, ${eng[0].period.toUpperCase()}: ${[...eng].sort((a, b) => (b.share ?? 0) - (a.share ?? 0)).map((e) => `${e.name} ${pc((e.share ?? 0) * 100)}${e.growth !== null ? ` (${(e.growth ?? 0) >= 0 ? "+" : ""}${pc((e.growth ?? 0) * 100)})` : ""}`).join(", ")}.` });
  else {
    if (d.model.revenueEngines.length) obs.push({ basis: "Reported", sources: ["Company model (revenue engines)"], text: `Revenue engines named in the records: ${d.model.revenueEngines.slice(0, 3).join("; ")}. Their size and growth are not quantified.` });
    gaps.push({ kind: "Missing data", text: "Revenue is not broken down by product, segment or region in the records, so the drivers of growth cannot be sized.", question: "What drives revenue growth? (needs a segment or geography revenue history)" });
  }
  if (d.model.customers.length) obs.push({ basis: "Reported", sources: ["Company model (customers)"], text: `Customers named in the records: ${d.model.customers.join(", ")}. Customer-concentration figures are not extracted into the records (the filing's notes may carry them).` });
  const rev = d.run("revenue_and_income", "revenue"), pat = d.run("revenue_and_income", "pat");
  if (rev.length >= 3) {
    const yoy = rev.slice(1).map((p, i) => ((p.v - rev[i].v) / rev[i].v) * 100);
    obs.push({ basis: "Calculated", sources: [fin(rev[rev.length - 1].fy), "Financial statements, multi-year"], text: `Revenue rose about ${pc(cagr(rev) ?? 0)} a year over ${span(rev)}, with year-on-year growth between ${pc(Math.min(...yoy))} and ${pc(Math.max(...yoy))}${pat.length >= 3 && cagr(pat) !== null ? `; profit rose about ${pc(cagr(pat) ?? 0)} a year` : ""}. No growth-category label (steady, fast, cyclical) is assigned: the figures describe the past and do not show how long the growth can last.` });
  } else gaps.push({ kind: "Missing data", text: "A growth profile cannot be described: fewer than three consecutive years are reported on one stated basis.", question: "How fast has the business grown, like for like? (needs a consistent multi-year series)" });
  const current = inputs.strategyThemes.filter((t) => t.current_status === "CURRENT_PRIORITY").map((t) => String(t.theme_name));
  const live = inputs.projects.filter((p) => (p.assessment as Obj | undefined)?.execution_status === "operational").length, part = inputs.projects.filter((p) => (p.assessment as Obj | undefined)?.execution_status === "partially_operational").length;
  if (current.length || live) obs.push({ basis: "Reported", sources: ["Strategy evolution record", "Projects registry"], link: { label: "Story", href: companyRoute(c.slug) }, text: `${current.length ? `Current management priorities: ${current.join("; ")}. ` : ""}${live || part ? `${live} ${live === 1 ? "project is" : "projects are"} reported operational and ${part} partially operational.` : ""}`.trim() });
  const eps = d.run("per_share", "eps_basic");
  const ps = [...d.perShare].reverse()[0];
  if (eps.length >= 2) obs.push({ basis: "Calculated", sources: [fin(eps[eps.length - 1].fy, "Per-share records")], text: `Earnings per share rose from ₹${r1(eps[0].v)} (FY${eps[0].fy}) to ₹${r1(eps[eps.length - 1].v)} (FY${eps[eps.length - 1].fy})${ps && /no_material/.test(String(ps.dilution_status)) ? "; no material dilution is detected" : ""}.` });
  gaps.push({ kind: "Missing data", text: "A price is needed to compare valuation with growth (a PEG-style test). The records hold none, so valuation relative to growth cannot be computed; the earnings-growth inputs above are ready for it.", question: "How does valuation compare with growth? (needs a market price)" });
  gaps.push({ kind: "Missing data", text: "Market size, share and industry dynamics are not extracted into the records, so the length of the growth runway cannot be assessed from them.", question: "Where could the next leg of growth come from? (needs pipeline and market-size evidence)" });
  const lenses = [{ name: "Simple explanation", available: !!what }, { name: "Revenue drivers", available: eng.length > 0 }, { name: "Customers", available: d.model.customers.length > 0 }, { name: "Growth profile", available: rev.length >= 3 }, { name: "Growth runway", available: current.length > 0 || live > 0 }, { name: "Per-share growth", available: eps.length >= 2 }, { name: "Valuation against growth", available: false }];
  void story;
  const takeaway = `${what ? "The business can be explained in a sentence from the records" : "A plain explanation of the business is not available"}${eng.length ? ", and its revenue drivers can be sized by region" : ", but its revenue drivers cannot be sized"}. ${rev.length >= 3 ? "Growth is documented" : "Growth cannot be documented like for like"}; where more of it could come from rests on stated priorities and projects rather than measured market opportunity. Valuation relative to growth cannot be tested without a price.`;
  return { lenses, observations: obs, uncertain: gaps, takeaway };
}

const BUILDERS: Record<SpecialistId, (c: Ctx) => Built> = { graham, fisher, buffett, munger, lynch };

export function buildPanel(i: PanelInputs): Panel {
  const bank = i.data.workingCapital.applicability === "not_economically_meaningful" && /bank/i.test(i.data.workingCapital.reason);
  const ctx: Ctx = {
    ...i, bank,
    ansLead: (q, max = 260) => (i.answers[q]?.simple_answer ? leadOf(String(i.answers[q].simple_answer), max) : null),
    ansSrc: (q) => `Approved answer: ${titleOf(q, i.catalog)}`,
    ansLink: (q, label) => (i.answers[q] ? { label: label ?? titleOf(q, i.catalog), href: questionRoute(i.slug, q) } : undefined),
  };
  const specialists = SPECIALISTS.map<SpecialistView>((s) => {
    const built = BUILDERS[s.id](ctx);
    // Each mapped question is a catalog question; its answer, if approved, lives under its certified id.
    const questions = s.questions.map<Investigate>((q) => {
      const cq = i.catalog.questions.find((x) => x.id === q.id);
      const cid = cq?.certifiedId ?? q.id;
      const ok = !!i.answers[cid];
      return { id: q.id, title: cq?.title ?? titleOf(q.id, i.catalog), why: q.why, status: ok ? "approved" : "not-approved", href: questionRoute(i.slug, ok ? cid : q.id), ...(ok ? { preview: leadOf(String(i.answers[cid].simple_answer ?? ""), 210) } : {}) };
    }).sort((a, b) => Number(b.status === "approved") - Number(a.status === "approved"));
    const first = built.uncertain[0];
    return { id: s.id, name: s.name, framework: s.framework, coreQuestion: s.coreQuestion, investorQuestion: s.investorQuestion, evaluates: s.evaluates, lenses: built.lenses, observations: built.observations, questions, proposed: s.proposed, uncertain: built.uncertain, takeaway: built.takeaway, openQuestion: first?.question ?? first?.text ?? "No open question recorded." };
  });
  return { slug: i.slug, company: i.company, available: Object.keys(i.answers), docs: i.story.docs, titles: i.story.titles, specialists };
}
