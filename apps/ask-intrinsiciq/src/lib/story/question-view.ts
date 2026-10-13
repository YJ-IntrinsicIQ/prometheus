// Presentation adapter for the investor question pages.
// Reads the stored (approved) answer plus existing structured records and shapes them into
// one reading journey: answer → explore → discover → evidence. It adds no conclusions of its own.
import { buildAccountability, type Accountability } from "./accountability";
import { buildConnections, type Connection } from "./connections";
import { buildDiscoveries, type Discovery, type Visual } from "./discoveries";
import type { CommitmentRow } from "./commitment-evidence";
import type { StoryInputs } from "./story-adapter";
import { containsForbiddenUiTerm } from "@/src/lib/prometheus/sanitizers";
import type { Related } from "@/src/lib/catalog/journey";

type Obj = Record<string, unknown>;

export { QUESTIONS } from "./questions";
import { QUESTIONS } from "./questions";

export type Body =
  | { kind: "visual"; visual: Visual }
  | { kind: "spans"; axis: [number, number]; rows: { label: string; full: string; from: number; to: number; state: string; note: string }[] }
  | { kind: "chains"; data: Accountability }
  | { kind: "connections"; items: Connection[] }
  | { kind: "commitments"; rows: CommitmentRow[] }
  | { kind: "consistency"; items: { label: string; status: string; text: string }[] };

export type Block = { id: string; title: string; caption: string; body: Body };

export type QuestionView = {
  slug: string;
  company: string;
  available: string[]; // questions with an approved answer, for navigation
  docs: string[]; // fiscal years whose annual report can be opened
  titles?: Record<string, string>; // titles of the approved questions, for related-question links in the page
  context?: { stage: string; familyId: string; familyTitle: string }; // where this question sits in the research journey
  related?: Related[]; // approved questions worth reading next, with the reason each follows
  next?: { label: string; href: string; blurb: string } | null; // the next stage of the journey
  panels?: { id: string; name: string; href: string }[]; // Investment Panel perspectives that use this question
  periodNote?: string; // set when a year in the answer is an as-of date or deadline beyond the latest annual report held
  question: { id: string; family: string; title: string };
  conclusion: string;
  takeaway: string;
  period: string;
  facts: { label: string; value: string; period: string; note?: string }[];
  notices: { id: string; title: string; text: string; items: string[] }[];
  blocks: Block[];
  discoveries: Discovery[];
  drilldown: {
    facts: string[];
    observations: string[];
    sources: string[];
    limitations: string[];
    monitor: string[];
    original: { label: string; value: unknown }[];
  };
};

export type QuestionInputs = StoryInputs & {
  questionId: string;
  question?: { id: string; family: string; title: string }; // for approved answers to catalog questions outside the original five
  answer: Obj;
  capital: Obj[];
  measurable: Obj[];
  tracker: Record<string, number> | null;
  revenueSeries: { year: string; value: number; basis: string }[];
};

// ── Plain-language cleaning ────────────────────────────────────────────────
const ENUM: Record<string, string> = {
  CURRENTLY_WORSENING: "currently worsening",
  HISTORICALLY_WORSENED_NOT_RECONFIRMED: "worsened earlier, not reconfirmed",
  HISTORICALLY_WORSENING: "worsened earlier",
  NOT_RECONFIRMED: "not reconfirmed",
  VERIFIABLE_COMMITMENT: "verifiable commitments",
  STRATEGIC_INTENT: "stated strategic intents",
  ASPIRATION: "strategic directions",
  FOLLOW_THROUGH_LARGELY_UNVERIFIED: "follow-through largely unverified",
  UNABLE_TO_VERIFY: "unable to verify",
  RECURRING: "recurring",
  IMPROVING: "improving",
  WORSENING: "worsening",
  INDICATIVE: "indicative",
  MISSED: "missed",
  CONSISTENT: "consistent",
  ANNOUNCED: "announced",
  MITIGATION_STARTED: "mitigation started",
  CURRENTLY_RE_ELEVATED: "elevated again",
  UNABLE_TO_ATTRIBUTE: "unable to attribute",
  SYSTEMIC_CONTEXT_ONLY: "sector-wide context only",
  SAME_RISK: "the same risk",
};

const KEEP = new Set(["EBITDA", "CRAR", "GNPA", "NNPA", "CAGR", "ROCE"]);
let LABELS = new Map<string, string>(); // commitment id -> short plain label, set per build
const commitmentLabel = (m: Obj) => {
  const subj = ((m.commitment_identity as Obj | undefined)?.named_subjects as Obj[] | undefined)?.[0]?.canonical;
  if (typeof subj === "string") return `${subj.charAt(0).toUpperCase()}${subj.slice(1)} commitment`;
  const w = String(m.original_statement ?? "").replace(/\.$/, "").split(/\s+/);
  return `“${w.slice(0, 5).join(" ")}${w.length > 5 ? "…" : ""}” commitment`;
};

export function plain(input: string): string {
  let t = String(input);
  t = t.replace(/\s*\((?:(?:MC|RG|PJ|CAO)-\d{2,}(?:,\s*)?)+\)/g, ""); // a bare list of identifiers carries no meaning for an investor
  t = t.replace(/(^|[^(\w])((?:MC)-\d{2,})\b(?!\s*\()/g, (m, pre, id) => `${pre}${LABELS.get(id) ?? ""}`);
  t = t.replace(/(^|[^(\w])(?:MC|RG|PJ|CAO)-\d{2,}\s*\(([^)]*)\)/g, "$1$2");
  t = t.replace(/\b(?:MC|RG|PJ|CAO|CL|CHK|MP|CM)-\d{2,}(?:,\s*)?/g, "");
  t = t.replace(/\b(?:risk|RISK)_(?:[0-9a-fA-F]{8,}|\d{3,})\b(?:\s*[;,])?/g, "").replace(/\b[a-z_]+:risk_[0-9a-f]+(?::[a-z_]+)?/g, "");
  t = t.replace(/\(\s*([,;]\s*)?/g, "(").replace(/\s+\)/g, ")").replace(/\(\s*\)/g, "");
  t = t.replace(/—\s*\((FY\d{2})\):/g, "— $1:").replace(/\s*\((FY\d{2}[–-]FY\d{2})\)\s*\(/g, " ($1; ");
  t = t.replace(/\bUnable To Verify\b/g, "unable to verify");
  t = t.replace(/(^|[.!?]\s+)canonical\s+([a-z])/gi, (_m, pre, c) => `${pre}${c.toUpperCase()}`).replace(/\bcanonically\b/gi, "formally").replace(/\bcanonical\s+/gi, ""); // internal vocabulary: "no canonical confirmation" reads "no confirmation"
  t = t.replace(/\bINR\s?([\d,]+(?:\.\d+)?)\s?(?:crore|cr)\b/gi, "₹$1 cr");
  t = t.replace(/\b[A-Z]{2,}(?:_[A-Z]{2,})+\b/g, (m) => ENUM[m] ?? m.toLowerCase().replace(/_/g, " "));
  t = t.replace(/\b[A-Z]{5,}\b/g, (m) => ENUM[m] ?? (KEEP.has(m) ? m : m.charAt(0) + m.slice(1).toLowerCase()));
  t = t.replace(/\b(in_progress)\b/g, "in progress").replace(/\bH([12])CY(\d{2})\b/g, "H$1 20$2");
  return t.replace(/\s{2,}/g, " ").replace(/\s+([,.;:])/g, "$1").replace(/^[\s:;,—-]+/, "").trim();
}

/** A short excerpt for a question list: whole sentences from the approved answer, screened for internal terms. Approved text only. */
export function previewText(answer: Obj, max = 170): string {
  LABELS = new Map(); // never reuse another company's identifier labels
  let t = lead(plain(String(answer.simple_answer ?? "")), max);
  if (t.length > max + 40) t = `${t.slice(0, max).replace(/[;,]?\s+\S*$/, "")}…`;
  return containsForbiddenUiTerm(t) ? "" : t;
}

/**
 * The years an answer rests on, split by what they are. A year after the company's latest annual report held locally is an
 * as-of date or a deadline, not filing evidence (e.g. "FY 2025-26" for a bank whose reports end at FY25).
 */
export function evidencePeriod(text: string, docs: string[]): { period: string; note: string } {
  const ys = [...text.matchAll(/FY\s?(?:20)?(\d{2})(?:\s?[-–]\s?(\d{2}))?(?!\d)/g)].map((m) => Number(m[2] ?? m[1]));
  if (!ys.length) return { period: "n/a", note: "" };
  const latest = Math.max(0, ...docs.map((d) => Number(/(\d{2})/.exec(d)?.[1] ?? 0)));
  const earliest = Math.min(...docs.map((d) => Number(/(\d{2})/.exec(d)?.[1] ?? 99)), 99);
  const lo = Math.max(Math.min(...ys), earliest === 99 ? 0 : earliest), hi = Math.max(...ys);   // evidence cannot start before the first annual report held
  if (!latest || hi <= latest) return { period: `FY${lo}–FY${hi}`, note: "" };
  const inFiling = ys.filter((y) => y <= latest);
  const period = inFiling.length ? `FY${Math.max(Math.min(...inFiling), lo)}–FY${Math.max(...inFiling)}` : `up to FY${latest}`;
  return { period, note: `FY${hi} appears only as an as-of date or a deadline. The latest annual report held for this company is FY${latest}, so it is not filing evidence.` };
}
/** A single fiscal year beyond the latest annual report is an as-of date, not an evidence period. */
const asOf = (period: string, docs: string[]) => {
  const latest = Math.max(0, ...docs.map((d) => Number(/(\d{2})/.exec(d)?.[1] ?? 0)));
  const m = /^FY(\d{2})$/.exec(period.trim());
  return latest && m && Number(m[1]) > latest ? `as of FY${m[1]} year-end` : period;
};

const sentences = (t: string) => t.split(/(?<=[a-z0-9)%”™]\.)\s+(?=[A-Z(])/).map((x) => x.trim());
function lead(t: string, max: number): string {
  const out: string[] = [];
  for (const s of sentences(t)) {
    if (out.join(" ").length + s.length > max && out.length) break;
    out.push(s);
  }
  return out.join(" ");
}

// ── Metric-card shaping: short value, units kept, scope/period in supporting text ──
const ACRONYM: Record<string, string> = { NPM: "Net profit margin", PAT: "Profit (PAT)", FCF: "Free cash flow", EBITDA: "EBITDA margin" };
const money = (s: string) => {
  const m = /(?:₹|INR\s?)\s?(-?[\d,]+(?:\.\d+)?)\s?(cr|crore)?/i.exec(s) ?? /^\s*(-?[\d,]+(?:\.\d+)?)\s?(cr|crore)\b/i.exec(s);
  return m ? { text: `₹${m[1]}${m[2] ? " Cr" : ""}`, n: Number(m[1].replace(/,/g, "")) } : null;
};
type Fact = QuestionView["facts"][number];

function shapeFact(label: string, raw: string, period: string): Fact[] {
  let v = plain(raw);
  // several "Label amount" metrics in one value -> separate tiles
  const segs = v.split(/;\s*(?![^()]*\))/);
  const labelled = segs.map((x) => /^([A-Za-z][A-Za-z /&-]{1,24}?)\s+((?:₹|INR)?\s?[\d,.]+\s?(?:cr|crore|%)?.*)$/.exec(x.trim()));
  if (segs.length >= 2 && labelled.every(Boolean))
    return labelled.map((m) => ({ label: ACRONYM[m![1].trim()] ?? m![1].trim(), value: money(m![2])?.text ?? m![2].trim(), period }));
  // progression statuses: "0 delivered / 2 in progress / 23 announced (of 25)"
  const pg = /^(\d+) delivered(?: \/ (\d+) partially[ _]delivered)? \/ (\d+) in[ _]progress \/ (\d+) announced \(of (\d+)\)$/.exec(v);
  if (pg) return [{ label: "Progression-tracker items confirmed delivered", value: `${pg[1]} of ${pg[5]}`, period, note: `${pg[2] ? `${pg[2]} partially delivered · ` : ""}${pg[3]} in progress · ${pg[4]} announced` }];
  // "A → B" ranges: show the latest, explain the start
  if (v.includes("→")) {
    const parts = v.split(/\s*→\s*/), from = parts[0], to = parts[parts.length - 1];
    const f = money(from), t = money(to);
    const fy = (x: string) => /FY\d{2}/.exec(x)?.[0];
    if (f && t) {
      const dir = t.n > f.n ? "up from" : t.n < f.n ? "down from" : "from";
      return [{ label: fy(to) ? `${label} · ${fy(to)}` : label, value: t.text, period: fy(to) ? "" : period, note: `${dir} ${f.text}${fy(from) ? ` in ${fy(from)}` : ""}` }];
    }
  }
  // amount followed by words / a parenthetical -> amount, with the rest as supporting text
  const am = /^((?:₹|INR)\s?[\d,.]+\s?(?:cr|crore))\s+([a-z][^(]*?)(?:\s*\(.*\))?$/i.exec(v);
  if (am) return [{ label, value: money(am[1])!.text, period, note: am[2].trim() }];
  // "46 total; 4 hard; 0 confirmed delivered" -> first part as value
  const dash = /^(\d[\d,.]*)\s+[—-]\s+(.*)$/.exec(v);
  if (dash) return [{ label, value: dash[1], period, ...(dash[2].length <= 90 ? { note: dash[2] } : {}) }];
  if (segs.length >= 2) return [{ label, value: segs[0], period, note: segs.slice(1).join("; ") }];
  const nw = /^(\d[\d,.]*)\s+([a-z][a-z /-]{2,28})$/.exec(v);
  if (nw && !/^cr/i.test(nw[2])) return [{ label, value: nw[1], period, note: nw[2] }];
  const par = /^([^()]+?)\s*\(([^)]*)\)$/.exec(v);
  if (par && par[1].length <= 14) return [{ label, value: par[1], period, note: par[2] }];
  const mm = money(v);
  return [{ label, value: mm && v.length <= 24 ? mm.text : v, period }];
}

function parseFacts(dpf: unknown[], maxLen = 34): QuestionView["facts"] {
  const out: QuestionView["facts"] = [];
  const push = (label: string, value: string, period: string) => {
    for (const f of shapeFact(plain(label).replace(/\s*\([^)]*\)\s*$/, "").trim(), value, period)) pushOne(f.label, f.value, f.period, f.note);
  };
  const pushOne = (label: string, value: string, period: string, note?: string) => {
    const l = plain(label), v = value;
    if (note && note.length > 60) return; // a tile that needs a paragraph is a drill-down item, not a metric
    if (!l || !v || v.length > maxLen || l.length > 56 || !/\d/.test(v) || /domain|\braw\b/i.test(l) || out.some((f) => f.label === l || (v.length > 6 && f.value === v))) return;
    out.push({ label: l.charAt(0).toUpperCase() + l.slice(1), value: v, period: period.replace(/\s*→\s*/g, "–").replace(/(FY\d{2})(?:–FY\d{2})+–(FY\d{2})/g, "$1–$2").replace(/\bfy(\d{2})\b/g, "FY$1"), ...(note ? { note } : {}) });
  };
  for (const e of dpf) {
    if (typeof e === "object" && e) push(String((e as Obj).metric ?? ""), String((e as Obj).value ?? ""), String((e as Obj).period ?? ""));
    else if (typeof e === "string" && e.length < 220 && /;/.test(e) && /\d/.test(e))
      for (const seg of e.split(/;\s*/)) {
        const m = /^(.+?):\s*(\d[\d,.]*)$/.exec(seg.trim());
        if (m) push(m[1], m[2], /FY\d{2}[–-]FY\d{2}/.exec(e)?.[0] ?? "");
      }
    if (out.length >= 5) break;
  }
  return out.slice(0, 5);
}

const fyRange = (t: string) => {
  const ys = [...t.matchAll(/FY(\d{2})/g)].map((m) => Number(m[1]));
  return ys.length ? `FY${Math.min(...ys)}–FY${Math.max(...ys)}` : "n/a";
};
const listOf = (v: unknown): string[] => (Array.isArray(v) ? v.map((x) => plain(typeof x === "string" ? x : JSON.stringify(x))) : v ? [plain(String(v))] : []);
const fyN = (p: unknown) => Number(/(\d{2})/.exec(String(p))?.[1] ?? 0);

// ── Per-question blocks, chosen from the evidence that exists ──
function blocksFor(q: string, inp: QuestionInputs, acct: Accountability, conns: Connection[]): Block[] {
  const ans = inp.answer;
  const blocks: Block[] = [];
  const add = (b: Block) => blocks.push(b);

  if (inp.commitmentRows.length && (q === "what-has-management-promised" || q === "what-did-management-actually-deliver"))
    add({ id: "commitment-evidence", title: "Commitments: tracker versus evidence", caption: "The tracker's status and the annual-report evidence, kept apart: execution, delivery, target achievement, economic outcome and what is still unknown.", body: { kind: "commitments", rows: inp.commitmentRows } });
  if (!inp.withholdCommitments) {
    if (q === "what-has-management-promised" && acct.chains.length) {
      add({ id: "overview", title: "Commitments with a checkable target", caption: "From the approved commitments register.",
        body: { kind: "visual", visual: { kind: "table", head: ["Year", "Commitment", "Due", "Approved record"], rows: acct.chains.map((c) => [c.year, c.promise, c.deadline ?? "not stated", c.status === "Not verified" ? "Unable to verify" : c.status]) } } });
      add({ id: "history", title: "Promise history", caption: "When each checkable promise was made.",
        body: { kind: "visual", visual: { kind: "timeline", items: acct.chains.map((c) => ({ when: c.year, text: `${c.promise}${c.deadline ? ` (due ${c.deadline})` : ""}` })) } } });
    }
    if (q === "what-did-management-actually-deliver" && acct.chains.length)
      add({ id: "chains", title: "Promise → Action → Outcome", caption: "Each checkable commitment from the approved register. No later-report evidence is available to link actions or outcomes, so none is shown.", body: { kind: "chains", data: acct } });
  }

  if (q === "what-could-go-wrong") {
    const themes = [...(inp.riskThemes ?? [])].sort((a, b) => fyN(a.first_seen_period) - fyN(b.first_seen_period));
    const order = ["WORSENING", "RECURRING", "IMPROVING"];
    const rank = (t: Obj) => { const i = order.indexOf(String(t.current_state)); return i === -1 ? 9 : i; };
    const word = (s: string) => ENUM[s] ?? s.toLowerCase().replace(/_/g, " ");
    const years = themes.flatMap((t) => [2000 + fyN(t.first_seen_period), 2000 + fyN(t.latest_seen_period)]);
    const axis: [number, number] = [Math.min(...years), Math.max(...years, Math.min(...years) + 2)];
    if (themes.length)
      add({ id: "evolution", title: "Risk evolution", caption: `First and latest year each risk theme was disclosed, FY${axis[0] % 100}–FY${axis[1] % 100}.`,
        body: { kind: "spans", axis, rows: themes.sort((a, b) => rank(a) - rank(b)).map((t) => ({
          label: ((x) => (x.length > 70 ? `${x.slice(0, 69).replace(/\s+\S*$/, "")}…` : x))(String(t.theme).replace(/^./, (c) => c.toUpperCase())),
          full: String(t.theme).replace(/^./, (c) => c.toUpperCase()), from: 2000 + fyN(t.first_seen_period), to: 2000 + fyN(t.latest_seen_period),
          state: word(String(t.current_state)), note: `${String(t.first_seen_period).toUpperCase()}–${String(t.latest_seen_period).toUpperCase()}` })) } });
    const fresh = themes.filter((t) => fyN(t.first_seen_period) === 26);
    if (fresh.length)
      add({ id: "changes", title: "Important changes in the latest year", caption: "Risks disclosed for the first time in FY26.",
        body: { kind: "visual", visual: { kind: "table", head: ["Risk", "First disclosed", "What it is"], rows: fresh.map((t) => ["" + String(t.theme).replace(/^./, (c) => c.toUpperCase()), "FY26", plain(String(t.risk_description ?? ""))]) } } });
  }

  if (q === "how-is-capital-allocated") {
    const attr = new Map((inp.attribution ?? []).map((c) => [String(c.source_action_id), String(c.attribution_strength)]));
    // The ledger marks which lines are real uses of capital; sources, balances and disposals are left out of the table.
    const kind = (a: Obj) => (String(a.deployment_eligibility).startsWith("INELIGIBLE") ? "skip" : String(a.deployment_eligibility).includes("AMBIGUOUS") ? "unclear" : "ok");
    const groups = new Map<string, Obj[]>();
    for (const a of inp.capital) if (kind(a) !== "skip") groups.set(`${a.allocation_category}|${kind(a)}`, [...(groups.get(`${a.allocation_category}|${kind(a)}`) ?? []), a]);
    const skipped = inp.capital.filter((a) => kind(a) === "skip").length;
    const label: Record<string, string> = { acquisition: "Acquisitions", debt_repayment: "Debt repayment", dividend: "Dividends", organic_capex: "Plants and capacity (capex)", share_buyback: "Share buybacks", working_capital: "Working capital loans", subsidiary_investment: "Subsidiary loans" };
    const rows = [...groups.entries()].map(([gk, xs]) => {
      const [k, kd] = gk.split("|");
      // The amount column sums amounts, so the years shown must be the years those amounts belong to (amount_period); only older
      // artifacts without it fall back to the deployment span.
      const stamped = xs.filter((x) => typeof x.amount === "number");
      const own = stamped.length > 0 && stamped.every((x) => typeof x.amount_period === "string");
      const yrs = own ? [...new Set(stamped.map((x) => fyN(x.amount_period)))].sort() : [...new Set(xs.flatMap((x) => (x.deployment_periods as string[]).map(fyN)))].sort();
      const amt = xs.reduce((s, x) => s + (typeof x.amount === "number" ? x.amount : 0), 0);
      const direct = xs.every((x) => attr.get(String(x.allocation_id)) === "DIRECTLY_ATTRIBUTABLE");
      const none = xs.every((x) => attr.get(String(x.allocation_id)) === "NO_OUTCOME_EVIDENCE");
      const name = k === "unknown" ? "Unclassified line items" : label[k] ?? plain(k.replace(/_/g, " "));
      return [`${name.charAt(0).toUpperCase()}${name.slice(1)}${kd === "unclear" ? " (classification unclear)" : ""}`, yrs[0] === yrs[yrs.length - 1] ? `FY${yrs[0]}` : `FY${yrs[0]}–FY${yrs[yrs.length - 1]}`, amt ? `₹${Math.round(amt).toLocaleString("en-IN")} cr` : "not stated", direct ? "The transaction is itself the economic event" : none ? "No outcome evidence in the records" : "Mixed"];
    });
    if (rows.length)
      add({ id: "deployment", title: "Capital deployment", caption: `Uses of capital in the ledger, and whether an outcome can be shown.${skipped ? ` ${skipped} other ledger lines (capital raised, balances, disposals) are not uses of capital and are left out.` : ""}`,
        body: { kind: "visual", visual: { kind: "table", head: ["Where capital went", "Years", "Amount", "Outcome evidence"], rows } } });
    const cc = conns.filter((c) => c.link?.href.endsWith("how-is-capital-allocated"));
    if (cc.length) add({ id: "chains", title: "Investment → economic outcome", caption: "Where the records connect capital to results, and where they stop.", body: { kind: "connections", items: cc } });
  }

  if (q === "how-good-is-management") {
    const map = (ans.management_consistency_map ?? {}) as Record<string, string>;
    const items = Object.entries(map).map(([label, t]) => {
      const m = /^([A-Za-z_ ]{2,40}?)\s+—\s+(.*)$/.exec(String(t));
      return { label, status: plain(m?.[1] ?? "") || "noted", text: plain(m?.[2] ?? String(t)) };
    });
    if (items.length)
      add({ id: "consistency", title: "Management consistency", caption: "How statements and actions line up, as recorded in the approved answer.", body: { kind: "consistency", items } });
  }
  return blocks;
}

const readableLinks = (v: unknown) =>
  (Array.isArray(v) ? v : []).map((r: Obj) => `${plain(String(r.rel_type ?? "").toLowerCase().replace(/_/g, " ")).replace(/^./, (c) => c.toUpperCase())} — confidence: ${plain(String(r.causal_confidence ?? "").toLowerCase())}; review outcome: ${plain(String(r.acceptance ?? "").toLowerCase().replace(/_/g, " "))}`);
const readableClaims = (v: unknown) => (Array.isArray(v) ? v : []).map((c: Obj) => plain(String(c.claim_text ?? "")));

const deep = (v: unknown): unknown =>
  typeof v === "string" ? plain(v) : Array.isArray(v) ? v.map(deep) : v && typeof v === "object" ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, deep(x)])) : v;

// Release-readiness check: the answer's status wording must agree with the commitment records.
function statusConflict(inp: QuestionInputs, acct: Accountability) {
  const flagged = inp.measurable.filter((m) => /DELAYED|MISSED/.test(String(m.delivery_status)));
  const text = JSON.stringify(inp.answer);
  // Only a positive count ("1 DELAYED") counts; "unknown ≠ MISSED" is a negation, not a status.
  const word = /\b\d+\s+DELAYED\b/.test(text) ? "delayed" : /\b\d+\s+MISSED\b/.test(text) ? "missed" : null;
  const recordsDelayed = acct.counts["Delayed or missed"] + (inp.tracker?.delayed ?? 0) + (inp.tracker?.missed ?? 0);
  if (!flagged.length || !word || recordsDelayed > 0) return null;
  const short = (t: string, n = 160) => (t.length > n ? `${t.slice(0, n).replace(/\s+\S*$/, "")}…` : t);
  const q = (m: Obj) => `“${short(plain(String(m.original_statement ?? "")))}” — extracted target: ${String(m.extracted_target ?? "n/a")}${m.target_period ? `, target period ${String(m.target_period).toUpperCase()}` : ""}; statement from ${String(m.source_period ?? "").toUpperCase()}`;
  const sameYear = flagged.some((m) => m.target_period && m.target_period === m.source_period);
  return {
    id: "status-conflict",
    title: "Status disagreement in the source records — flagged for release review",
    text: `This answer reports ${flagged.length} of ${inp.measurable.length} measurable commitments as ${word}. The commitments register and the promise tracker record none as delayed or missed (all unable to verify), and the records do not establish a missed deadline. The answer is shown unchanged; this is unresolved.`,
    items: [
      ...flagged.map(q),
      `The answer's measurable commitments come from the management-progression tracker. The register's ${acct.total} checkable commitments are a different set: ${acct.chains.map((c) => short(c.promise.toLowerCase().replace(/\s*\(.*$/, ""), 80)).join("; ")}.`,
      ...(sameYear ? ["For the flagged item the target period is the same year as the statement itself, so it reads as a reported result, not a forward deadline."] : []),
    ],
  };
}

export function buildQuestionView(inp: QuestionInputs): QuestionView | null {
  LABELS = new Map(inp.commitments.map((m) => [String(m.id), commitmentLabel(m)]));
  const question = inp.question ?? QUESTIONS.find((x) => x.id === inp.questionId);
  if (!question || !inp.answer) return null;
  const a = inp.answer;
  const acct = buildAccountability(inp);
  const conns = buildConnections(inp);
  const all = buildDiscoveries(inp);
  const discoveries = all.filter((d) => d.links.some((l) => l.href.endsWith(`/${question.id}`)));
  const text = [a.simple_answer, ...(Array.isArray(a.deterministic_precision_facts) ? a.deterministic_precision_facts.map((x) => JSON.stringify(x)) : [])].join(" ");
  const blocks = blocksFor(question.id, inp, acct, conns);
  let facts = ((d) => { const f = parseFacts(d); return f.length >= 3 ? f : parseFacts(d, 64); })(Array.isArray(a.deterministic_precision_facts) ? a.deterministic_precision_facts : []);
  if (facts.length < 3 && question.id === "what-could-go-wrong" && (inp.riskThemes ?? []).length) {
    const by = new Map<string, number>();
    for (const t of (inp.riskThemes ?? [])) by.set(String(t.current_state), (by.get(String(t.current_state)) ?? 0) + 1);
    const w = (k: string) => (ENUM[k] ?? k.toLowerCase().replace(/_/g, " "));
    facts = [{ label: "Risk themes tracked", value: String((inp.riskThemes ?? []).length), period: fyRange(JSON.stringify((inp.riskThemes ?? []).map((t) => [t.first_seen_period, t.latest_seen_period]).flat()).toUpperCase()) },
      ...[...by.entries()].filter(([k]) => !/NOT_RECONFIRMED/.test(k)).sort((x, y) => y[1] - x[1]).slice(0, 3).map(([k, n]) => ({ label: `Risks ${w(k)}`, value: String(n), period: "latest year" }))];
  }
  // Data-integrity guards: neither changes the stored answer; they only decide what the new UI displays.
  const notices: QuestionView["notices"] = [];
  const conflict = statusConflict(inp, acct);
  if (conflict) {
    notices.push(conflict);
    facts = facts.filter((f) => !/delayed|missed/i.test(`${f.label} ${f.value} ${f.note ?? ""}`)); // disputed metric stays out of the summary
  }
  const rs = inp.revenueSeries;
  const first = rs[0], last = rs[rs.length - 1];
  if (rs.length >= 2 && first.basis !== last.basis && last.value / first.value >= 5) {
    const fyLabel = (y: string) => y.toUpperCase();
    const cr = (n: number) => `₹${Math.round(n).toLocaleString("en-IN")} Cr`;
    let hit = false;
    facts = facts.map((f) => {
      if (!/^revenue/i.test(f.label) || !/^(up|down) from/.test(f.note ?? "")) return f;
      hit = true;
      return { ...f, label: `Revenue · ${fyLabel(last.year)}`, period: "", note: `${last.basis} basis` };
    });
    if (hit)
      notices.push({
        id: "data-flag-revenue",
        title: "Revenue comparison withheld — flagged for later correction",
        text: `The approved answer compares revenue across ${fyLabel(first.year)}–${fyLabel(last.year)}. In the financial records the ${fyLabel(first.year)} figure is on a "${first.basis}" basis and the ${fyLabel(last.year)} figure is "${last.basis}", across a merger that changes the reporting scope. The two are not comparable, so the comparison is not shown here. The stored answer is unchanged.`,
        items: rs.map((p) => `${fyLabel(p.year)}: ${cr(p.value)} (${p.basis} basis)`),
      });
  }
  const ep = evidencePeriod(text, inp.docs);
  const sources = [...new Set([
    "Approved answer for this question",
    ...(blocks.length ? ["Approved records"] : []),
    ...blocks.flatMap((b) => (b.body.kind === "chains" ? b.body.data.chains.flatMap((c) => c.evidence) : [])),
    ...conns.flatMap((c) => c.nodes.flatMap((n) => n.evidence)).filter((e) => blocks.some((b) => b.body.kind === "connections" && b.body.items.some((c) => c.nodes.some((n) => n.evidence.includes(e))))),
  ])];
  return {
    slug: inp.slug,
    company: inp.company,
    available: inp.available,
    docs: inp.docs,
    question,
    conclusion: lead(plain(String(a.simple_answer ?? "")), 300),
    takeaway: lead(plain(String(a.what_may_mean_economically ?? a.investor_interpretation ?? "")), 260),
    period: ep.period,
    periodNote: ep.note || undefined,
    titles: inp.titles,
    facts: facts.map((f) => ({ ...f, period: asOf(f.period, inp.docs) })),
    notices,
    blocks,
    discoveries,
    drilldown: {
      facts: [...(conflict ? ["Status note: the “delayed” count in this answer is disputed by the commitment records; see the note at the top of the page."] : []), ...listOf(a.key_points)],
      observations: listOf(a.what_evidence_shows),
      sources,
      limitations: listOf(a.what_is_not_yet_proven),
      monitor: listOf(a.what_to_monitor),
      original: Object.entries(a)
        .filter(([k]) => k !== "behavioral_descriptor") // technical metadata, not investor-facing
        .filter(([k]) => !["claims", "relationships", "evidence_gaps"].includes(k) || (Array.isArray(a[k]) && (a[k] as unknown[]).length))
        .map(([k, v]) => ({ label: k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()), value: k === "relationships" ? readableLinks(v) : k === "claims" ? readableClaims(v) : deep(v) })),
    },
  };
}
