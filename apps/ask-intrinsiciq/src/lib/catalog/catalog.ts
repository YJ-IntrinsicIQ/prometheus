import path from "node:path";
import { readJsonIfExists } from "@/src/lib/prometheus/read-json";
import { getRepoRoot } from "@/src/lib/ask-intrinsiciq/paths";
import { COMPANIES } from "@/src/lib/story/companies";
import { QUESTIONS } from "@/src/lib/story/questions";
import { SPECIALISTS, type SpecialistId } from "@/src/lib/panel/specialists";
import { VETTED_ALIASES } from "./journey";

/**
 * The canonical question catalog, read from the artifacts the catalog already produces — not a second list:
 *  - the category catalog (families, ids, titles) from each company's generated research view, which comes from the
 *    Python QUESTION_CATALOG (the views are identical across companies; a test enforces it), and
 *  - the answer dependency registry (governance), which names every registered question, what it draws on, and which
 *    certified question succeeded a catalog question ("shadow_family_note").
 * Listing a question here says nothing about whether it has an approved answer; that is decided per company elsewhere.
 */
type Obj = Record<string, unknown>;
export type QuestionBasis = "Computed from stored records" | "Stored records plus written analysis" | "Written analysis";
export type CatalogQuestion = {
  id: string; // the catalog id
  title: string;
  shortLabel: string;
  family: string; // family id
  drawsOn: string[];
  basis: QuestionBasis;
  certifiedId: string | null; // the id under which an approved answer to this question lives, if the question has one
  inCategoryCatalog: boolean; // false: registered in the dependency registry but absent from the category catalog
  specialists: SpecialistId[];
};
export type CatalogFamily = { id: string; title: string; description: string; questions: CatalogQuestion[] };
export type Catalog = { families: CatalogFamily[]; questions: CatalogQuestion[] };

const MODULES: Record<string, string> = { pcim: "investor intelligence model", cim: "company intelligence model", risk_registry: "risk register", gold_promise_tracker: "promise tracker" };
const human = (m: string) => MODULES[m] ?? m.replace(/_analysis$/, " panel analysis").replace(/_/g, " ");
const BASIS: Record<string, QuestionBasis> = { A_DETERMINISTIC: "Computed from stored records", C_HYBRID: "Stored records plus written analysis", B_LLM_REQUIRED: "Written analysis" };
const CERT = new Set<string>(QUESTIONS.map((q) => q.id));
let cache: { key: string; value: Catalog } | null = null;

export async function loadCatalog(opts: { repoRoot?: string } = {}): Promise<Catalog> {
  const root = opts.repoRoot ?? getRepoRoot();
  const key = root;
  if (cache && cache.key === key) return cache.value;
  const registry = await readJsonIfExists<{ questions?: Record<string, { class?: string; upstream_modules?: string[]; shadow_family_note?: string }> }>(path.join(root, "governance", "answer_dependency_registry.json"));
  let view: { categories?: { id: string; title: string; shortDescription?: string; questions: { id: string; title: string; shortLabel?: string }[] }[] } | null = null;
  for (const c of Object.values(COMPANIES)) {
    view = await readJsonIfExists(path.join(root, "companies", c.key, "company_memory", "ask_intrinsiciq", "company_research_view.json"));
    if (view?.categories?.length) break;
  }
  const reg = registry?.questions ?? {};
  const make = (id: string, title: string, shortLabel: string, family: string, inCat: boolean): CatalogQuestion => {
    const r = reg[id] ?? {};
    const alias = /^Shadow canary version \(([a-z-]+)\)/.exec(r.shadow_family_note ?? "")?.[1];
    return {
      id, title, shortLabel, family, inCategoryCatalog: inCat,
      drawsOn: [...new Set((r.upstream_modules ?? []).map(human))],
      basis: BASIS[r.class ?? ""] ?? "Stored records plus written analysis",
      certifiedId: CERT.has(id) ? id : alias && CERT.has(alias) && VETTED_ALIASES[id] === alias ? alias : null,
      specialists: SPECIALISTS.filter((s) => s.questions.some((q) => q.id === id)).map((s) => s.id),
    };
  };
  const families: CatalogFamily[] = (view?.categories ?? []).map((c) => ({ id: c.id, title: c.title, description: c.shortDescription ?? "", questions: c.questions.map((q) => make(q.id, q.title, q.shortLabel ?? q.title, c.id, true)) }));
  // Registered questions that the category catalog does not list (e.g. how-good-is-management) join the family of their purpose.
  const listed = new Set(families.flatMap((f) => f.questions.map((q) => q.id)));
  for (const id of Object.keys(reg).filter((q) => !listed.has(q))) {
    const cert = QUESTIONS.find((q) => q.id === id);
    const home = families.find((f) => f.id === "management") ?? families[0];
    home?.questions.push(make(id, cert?.title ?? id.replace(/-/g, " ").replace(/^./, (c) => c.toUpperCase()), cert?.family ?? id, home.id, false));
  }
  // Certified questions that no catalog question genuinely stands for (e.g. "What did management actually deliver?") are
  // registered questions in their own right, listed with the family of their purpose.
  const served = new Set(families.flatMap((f) => f.questions.map((q) => q.certifiedId)));
  for (const cq of QUESTIONS.filter((q) => !served.has(q.id))) {
    const home = families.find((f) => f.id === "management") ?? families[0];
    home?.questions.push({ ...make(cq.id, cq.title, cq.family, home.id, false), certifiedId: cq.id });
  }
  const value = { families, questions: families.flatMap((f) => f.questions) };
  cache = { key, value };
  return value;
}

/** Find a question by its catalog id OR by the id of the certified answer that serves it. */
export function findQuestion(catalog: Catalog, id: string): { q: CatalogQuestion; viaCertified: boolean } | null {
  const direct = catalog.questions.find((q) => q.id === id);
  if (direct) return { q: direct, viaCertified: false };
  const cert = catalog.questions.find((q) => q.certifiedId === id);
  return cert ? { q: cert, viaCertified: true } : null;
}
