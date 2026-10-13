import path from "node:path";
import { readJsonIfExists } from "@/src/lib/prometheus/read-json";
import { getRepoRoot } from "@/src/lib/ask-intrinsiciq/paths";
import { approvalGate } from "./approval-gate";
import { loadStoryInputs } from "./load-story";
import { loadCatalog, findQuestion } from "@/src/lib/catalog/catalog";
import { buildQuestionView, QUESTIONS, type QuestionView } from "./question-view";
import { nextStage, relatedFor, stageOfFamily } from "@/src/lib/catalog/journey";
import { SPECIALISTS } from "@/src/lib/panel/specialists";

type Obj = Record<string, unknown>;

/**
 * Read-only. The answer comes from the company's stored hybrid artifact and must pass the approval gate
 * (PASS/COMPLETE, approval record, fingerprint, full-artifact digest, validated customer text). An answer that
 * fails is not shown (null) — the page then states honestly that it is not available. No unapproved or shadow
 * candidate is ever read here.
 */
export async function loadQuestionView(slug: string, questionId: string, opts: { repoRoot?: string } = {}): Promise<QuestionView | null> {
  const hit = findQuestion(await loadCatalog({ repoRoot: opts.repoRoot }), questionId);
  if (!hit) return null; // not a catalog question: nothing to show
  const base = await loadStoryInputs(slug, opts);
  if (!base || !base.available.includes(questionId)) return null; // fail closed
  const mem = path.join(opts.repoRoot ?? getRepoRoot(), "companies", base.key, "company_memory");
  const [hybrid, registry, capital, progression, tracker, trends] = await Promise.all([
    readJsonIfExists<{ company_slug?: string; answers?: Record<string, { status?: string; coverage?: string; answer?: Obj }> }>(path.join(mem, "ask_intrinsiciq", "shadow_level3_hybrid_answers.json")),
    readJsonIfExists<{ approvals?: Record<string, Obj> }>(path.join(opts.repoRoot ?? getRepoRoot(), "governance", "approval_registry.json")),
    readJsonIfExists<{ allocations?: Obj[] }>(path.join(mem, "capital_allocation_outcomes", "capital_allocation_outcomes.json")),
    readJsonIfExists<{ measurable_commitments?: Obj[] }>(path.join(mem, "management_progression", "management_progression.json")),
    readJsonIfExists<{ summary?: { status_breakdown?: Record<string, number> } }>(path.join(mem, "gold", "management_promise_tracker.json")),
    readJsonIfExists<{ trend_groups?: { revenue_and_income?: { revenue?: { series?: Obj[] } } } }>(path.join(mem, "financials", "financial_trends.json")),
  ]);
  if (hybrid?.company_slug && hybrid.company_slug !== base.key) return null; // never cross companies
  const entry = hybrid?.answers?.[questionId];
  if (!entry?.answer) return null;
  if (!approvalGate(entry, registry?.approvals?.[`${base.key}:${questionId}`] as never).ok) return null;
  const catalog = await loadCatalog({ repoRoot: opts.repoRoot });
  const familyTitle = catalog.families.find((f) => f.id === hit.q.family)?.title ?? hit.q.family;
  const view = buildQuestionView({
    ...base,
    questionId,
    question: QUESTIONS.find((q) => q.id === questionId) ?? { id: questionId, family: familyTitle, title: hit.q.title },
    answer: entry.answer,
    capital: capital?.allocations ?? [],
    measurable: progression?.measurable_commitments ?? [],
    tracker: tracker?.summary?.status_breakdown ?? null,
    revenueSeries: (trends?.trend_groups?.revenue_and_income?.revenue?.series ?? []).map((p) => ({ year: String(p.year), value: Number(p.value), basis: String(p.basis ?? "unknown") })),
  });
  if (!view) return null;
  // Where this question sits in the research journey, and what to read next: only approved questions for THIS company are offered.
  return {
    ...view,
    context: { stage: stageOfFamily(hit.q.family)?.label ?? familyTitle, familyId: hit.q.family, familyTitle },
    related: relatedFor(catalog, base.available, slug, questionId),
    next: nextStage(catalog, base.available, slug, hit.q.family),
    panels: hit.q.specialists.map((id) => ({ id, name: SPECIALISTS.find((s) => s.id === id)!.name, href: `/company/${slug}/panel/${id}` })),
  };
}
