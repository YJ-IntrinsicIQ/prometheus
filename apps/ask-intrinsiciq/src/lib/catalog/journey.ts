// The investor research journey over the EXISTING catalog: no new questions, no new facts. It only decides what to suggest
// reading next. Two sources, in this order:
//  1. NEXT — a small, explicit table of research progressions between catalog questions (a promise is tested by its
//     delivery; profit is tested by cash). Each entry names a question that already exists in the catalog.
//  2. Relationships the catalog already records — questions that draw on the same stored records, that the same Investment
//     Panel specialist uses, or that sit in the same research family.
// A suggestion is offered only when the target has an approved answer for THIS company; nothing else is ever linked.
import { questionRoute } from "@/src/lib/routes";
import type { Catalog, CatalogQuestion } from "./catalog";

export type Stage = { id: string; label: string; blurb: string; families: string[]; panel?: boolean };
export const JOURNEY: Stage[] = [
  { id: "understand", label: "Understand the business", blurb: "What it does, who pays, how it earns.", families: ["understand-the-business"] },
  { id: "financials", label: "Explore the financials", blurb: "Cash, owner earnings, working capital, per-share economics.", families: ["financials"] },
  { id: "management", label: "Evaluate management", blurb: "Promises, delivery, capital allocation, incentives.", families: ["management"] },
  { id: "risks", label: "Examine the risks", blurb: "What could go wrong, and what to ask next.", families: ["risks-and-diligence"] },
  { id: "frameworks", label: "Apply investment frameworks", blurb: "Five specialist perspectives on the same evidence.", families: ["committee-view", "investor-panel"], panel: true },
];
export const stageOfFamily = (family: string): Stage | undefined => JOURNEY.find((s) => s.families.includes(family));

/** question -> [next question, why it follows]. Ids are catalog ids. */
export const NEXT: Record<string, [string, string][]> = {
  "what-does-company-do": [["who-are-the-customers", "Who pays for what it does."], ["how-does-it-make-money", "How the business turns that into revenue."]],
  "who-are-the-customers": [["how-does-it-make-money", "How customers translate into revenue."], ["what-does-company-do", "The business those customers buy from."]],
  "how-does-it-make-money": [["are-profits-converting-into-cash", "Whether that revenue ends up as cash."], ["who-are-the-customers", "Who the revenue comes from."]],
  "are-profits-converting-into-cash": [["what-is-owner-earnings", "What is left for owners after capital spending."], ["is-working-capital-a-concern", "Whether cash is tied up in receivables and inventory."], ["are-per-share-economics-improving", "What this means per share."]],
  "what-is-owner-earnings": [["are-profits-converting-into-cash", "The reported cash conversion behind it."], ["how-is-capital-allocated", "Where the cash went."], ["what-is-the-return-on-capex", "What capital spending has earned."]],
  "is-working-capital-a-concern": [["are-profits-converting-into-cash", "How working capital shows up in cash."], ["what-is-owner-earnings", "The cash left for owners."]],
  "are-per-share-economics-improving": [["what-is-owner-earnings", "The owner-earnings view of the same economics."], ["how-is-capital-allocated", "Buybacks, dividends and reinvestment."]],
  "what-has-management-promised": [["what-did-management-actually-deliver", "The test of those promises."], ["which-promises-are-overdue", "Which deadlines have passed."], ["what-promise-types-dominate", "How firm the promises are."]],
  "what-promise-types-dominate": [["what-has-management-promised", "The promises themselves."], ["which-promises-are-overdue", "Which dated promises have come due."]],
  "which-promises-are-overdue": [["what-was-missed", "Whether any was actually missed."], ["what-did-management-actually-deliver", "What was delivered."]],
  "what-did-management-actually-deliver": [["what-was-missed", "What the records show was missed."], ["did-past-claims-come-true", "Whether past claims held up."], ["did-execution-lead-to-outcomes", "Whether delivery produced results."]],
  "what-was-delivered-last-3-years": [["what-did-management-actually-deliver", "The longer record."], ["did-execution-lead-to-outcomes", "Whether recent delivery produced results."]],
  "what-was-missed": [["which-promises-are-overdue", "Deadlines that have passed."], ["did-past-claims-come-true", "How past claims held up overall."]],
  "did-past-claims-come-true": [["what-did-management-actually-deliver", "The delivery record."], ["did-execution-lead-to-outcomes", "Whether execution produced results."], ["how-good-is-management", "The overall management picture."]],
  "did-execution-lead-to-outcomes": [["which-investments-created-value", "Whether capital deployed created value."], ["what-projects-are-underway", "The projects behind the execution."], ["how-is-capital-allocated", "Where the capital went."]],
  "what-projects-are-underway": [["how-is-capacity-changing", "Capacity the projects add."], ["what-is-the-return-on-capex", "What spending on them has returned."], ["did-execution-lead-to-outcomes", "Whether execution has produced outcomes."]],
  "how-is-capacity-changing": [["what-projects-are-underway", "The projects that change capacity."], ["what-is-the-return-on-capex", "What the capital has earned."]],
  "what-is-management-commentary-saying": [["what-has-management-promised", "What it has committed to."], ["what-projects-are-underway", "Whether the stated priorities have projects behind them."]],
  "how-is-capital-allocated": [["which-investments-created-value", "Which allocations created value."], ["what-is-the-return-on-capex", "The return on capital spending."], ["what-is-owner-earnings", "The cash available to allocate."]],
  "which-investments-created-value": [["what-is-the-return-on-capex", "The capex part of the question."], ["how-is-capital-allocated", "The allocation behind it."], ["what-remains-unresolved", "What the records leave open."]],
  "what-is-the-return-on-capex": [["which-investments-created-value", "Value created more broadly."], ["what-is-owner-earnings", "Capital spending in owner earnings."], ["how-is-capacity-changing", "The capacity it paid for."]],
  "what-incentives-matter": [["how-good-is-management", "How management has behaved."], ["how-is-capital-allocated", "What its capital decisions show."]],
  "how-good-is-management": [["what-has-management-promised", "Its promises."], ["what-did-management-actually-deliver", "Its delivery."], ["what-needs-management-clarification", "What it still needs to explain."]],
  "what-could-go-wrong": [["what-regulatory-risks-remain-active", "The regulatory risks still active."], ["what-evidence-would-change-the-view", "What would change the assessment."], ["what-needs-management-clarification", "What to ask management."]],
  "what-can-break-the-thesis": [["what-regulatory-risks-remain-active", "The regulatory risks still active."], ["what-evidence-would-change-the-view", "What would change the assessment."], ["what-needs-management-clarification", "What to ask management."]],
  "what-regulatory-risks-remain-active": [["what-could-go-wrong", "The full risk record."], ["what-needs-management-clarification", "What to ask management."], ["what-remains-unresolved", "What is still open."]],
  "which-disclosure-is-missing": [["what-should-i-ask-ir", "Turning gaps into questions."], ["what-needs-management-clarification", "What management should clarify."]],
  "what-evidence-would-change-the-view": [["what-remains-unresolved", "What is still open."], ["what-could-go-wrong", "The risks behind it."]],
  "what-needs-management-clarification": [["what-should-i-ask-ir", "Questions for investor relations."], ["what-remains-unresolved", "What is still open."], ["what-has-management-promised", "The promises behind them."]],
  "what-should-i-ask-ir": [["what-needs-management-clarification", "What management needs to clarify."], ["what-remains-unresolved", "What is still open."]],
  "what-remains-unresolved": [["what-needs-management-clarification", "What management should clarify."], ["what-could-go-wrong", "The risks behind the open points."]],
};

export type Related = { id: string; title: string; href: string; why: string };

// A catalog question is served by a certified answer ONLY if that answer genuinely covers the question as asked (M59 review).
//  - what-can-break-the-thesis <- what-could-go-wrong: the approved risk record is the risk answer for that family: accepted.
//  - what-was-delivered-last-3-years <- what-did-management-actually-deliver: REJECTED. The approved answer covers every
//    commitment across FY20–FY26, not the last three years; the question needs its own answer.
export const VETTED_ALIASES: Record<string, string> = { "what-can-break-the-thesis": "what-could-go-wrong" };

/** Client-safe: the next questions after `anchor` that have an approved answer for this company, with the reason each follows. */
export function nextInline(anchor: string, available: string[], titles: Record<string, string>, limit = 3): { id: string; title: string; why: string }[] {
  const key = NEXT[anchor] ? anchor : Object.entries(VETTED_ALIASES).find(([, v]) => v === anchor)?.[0] ?? anchor;
  const self = VETTED_ALIASES[key] ?? key;
  return (NEXT[key] ?? [])
    .map(([id, why]) => ({ id: VETTED_ALIASES[id] ?? id, why }))
    .filter((x) => x.id !== self && available.includes(x.id) && titles[x.id])
    .slice(0, limit)
    .map((x) => ({ ...x, title: titles[x.id] }));
}

/** The id under which a catalog question's approved answer is served, if it has one. */
export const servedId = (q: CatalogQuestion) => q.certifiedId ?? q.id;

/**
 * Up to `limit` approved questions worth reading after `questionId`, each with the reason it follows. Only questions whose
 * answer is approved for this company are returned (`available` holds those ids); self-references are dropped.
 */
export function relatedFor(catalog: Catalog, available: string[], slug: string, questionId: string, limit = 4): Related[] {
  const byId = new Map<string, CatalogQuestion>();
  for (const q of catalog.questions) { byId.set(servedId(q), q); byId.set(q.id, q); }   // a target may be named by its catalog id or by the certified id that serves it
  const here = catalog.questions.find((q) => q.id === questionId || servedId(q) === questionId);
  if (!here) return [];
  const self = servedId(here);
  const out: Related[] = [];
  const seen = new Set<string>([self]);
  const add = (q: CatalogQuestion | undefined, why: string) => {
    if (!q || out.length >= limit) return;
    const sid = servedId(q);
    if (seen.has(sid) || !available.includes(sid)) return;
    seen.add(sid);
    out.push({ id: sid, title: q.title, href: questionRoute(slug, sid), why });
  };
  for (const [id, why] of NEXT[here.id] ?? NEXT[self] ?? []) add(byId.get(id), why);
  // relationships the catalog already records
  const mine = new Set(here.drawsOn);
  const scored = catalog.questions
    .filter((q) => servedId(q) !== self)
    .map((q) => {
      const shared = q.drawsOn.filter((m) => mine.has(m));
      const panel = q.specialists.filter((s) => here.specialists.includes(s));
      const score = shared.length * 2 + panel.length * 2 + (q.family === here.family ? 1 : 0);
      const why = shared.length ? `Draws on the same records (${shared.slice(0, 2).join(", ")}).` : panel.length ? "Used by the same Investment Panel perspective." : "Same research area.";
      return { q, score, why };
    })
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score);
  for (const x of scored) add(x.q, x.why);
  return out;
}

/** Where to go once this area has been read: the first approved question of the next stage, or the Investment Panel. */
export function nextStage(catalog: Catalog, available: string[], slug: string, family: string): { label: string; href: string; blurb: string } | null {
  const i = JOURNEY.findIndex((s) => s.families.includes(family));
  if (i < 0) return null;
  for (const s of JOURNEY.slice(i + 1)) {
    if (s.panel) return { label: s.label, href: `/company/${slug}/panel`, blurb: s.blurb };
    const q = catalog.questions.find((x) => s.families.includes(x.family) && available.includes(servedId(x)));
    if (q) return { label: s.label, href: questionRoute(slug, servedId(q)), blurb: s.blurb };
  }
  return null;
}
