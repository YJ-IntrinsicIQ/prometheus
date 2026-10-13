import path from "node:path";
import { getRepoRoot } from "@/src/lib/ask-intrinsiciq/paths";
import { availableAnnualReports } from "@/src/lib/evidence/documents";
import { readJsonIfExists } from "@/src/lib/prometheus/read-json";
import { questionRoute } from "@/src/lib/routes";
import { approvalGate } from "@/src/lib/story/approval-gate";
import { approvedQuestionIds } from "@/src/lib/story/authorization";
import { COMPANIES } from "@/src/lib/story/companies";
import { previewText } from "@/src/lib/story/question-view";
import { loadAbsenceLedger, withAbsence } from "@/src/lib/provenance/absence";
import { loadCatalog, type CatalogFamily, type CatalogQuestion } from "./catalog";
import { JOURNEY } from "./journey";

export type ExplorerQuestion = CatalogQuestion & { status: "approved" | "pending"; href: string; preview?: string };
export type StageSummary = { id: string; label: string; blurb: string; approved: number; total: number; panel: boolean; start: { title: string; href: string } | null };
export type Explorer = {
  slug: string; company: string; available: string[]; docs: string[];
  titles: Record<string, string>; // titles of the approved questions only
  stages: StageSummary[];
  families: (Omit<CatalogFamily, "questions"> & { questions: ExplorerQuestion[]; approved: number })[];
  totals: { questions: number; approved: number; pending: number };
};

type Hybrid = { company_slug?: string; answers?: Record<string, { status?: string; coverage?: string; answer?: Record<string, unknown> }> };

/**
 * Every catalog question for one company, each marked approved or pending. A question is "approved" only if its answer
 * passes the existing approval gate for THIS company (approvedQuestionIds); listing a question never makes it available.
 * Approved questions come first within each research area and carry a short excerpt of the approved answer itself; a
 * pending question carries nothing but its catalog description.
 */
export async function loadExplorer(slug: string): Promise<Explorer | null> {
  if (!COMPANIES[slug]) return null;
  const key = COMPANIES[slug].key;
  const root = getRepoRoot();
  const [catalog, available, hybrid, registry] = await Promise.all([
    loadCatalog(), approvedQuestionIds(slug),
    readJsonIfExists<Hybrid>(path.join(root, "companies", key, "company_memory", "ask_intrinsiciq", "shadow_level3_hybrid_answers.json")),
    readJsonIfExists<{ approvals?: Record<string, never> }>(path.join(root, "governance", "approval_registry.json")),
  ]);
  const own = !hybrid?.company_slug || hybrid.company_slug === key;   // never read another company's file
  const preview = (served: string): string | undefined => {
    const entry = own ? hybrid?.answers?.[served] : undefined;
    if (!entry?.answer || !approvalGate(entry, registry?.approvals?.[`${key}:${served}`]).ok) return undefined;
    return previewText(entry.answer) || undefined;
  };
  const titles: Record<string, string> = {};
  const families = catalog.families.map((f) => {
    const questions = f.questions.map<ExplorerQuestion>((q) => {
      const served = q.certifiedId ?? q.id;
      const ok = available.includes(served);
      if (ok) titles[served] ??= q.title;
      return { ...q, status: ok ? "approved" : "pending", href: questionRoute(slug, ok ? served : q.id), ...(ok ? { preview: preview(served) } : {}) };
    });
    const ordered = [...questions.filter((q) => q.status === "approved"), ...questions.filter((q) => q.status === "pending")]; // available first, catalog order kept within each group
    return { ...f, questions: ordered, approved: ordered.filter((q) => q.status === "approved").length };
  });
  const total = families.reduce((n, f) => n + f.questions.length, 0), approved = families.reduce((n, f) => n + f.approved, 0);
  const stages = JOURNEY.map<StageSummary>((s) => {
    const qs = families.filter((f) => s.families.includes(f.id)).flatMap((f) => f.questions);
    const first = qs.find((q) => q.status === "approved");
    return { id: s.id, label: s.label, blurb: s.blurb, approved: qs.filter((q) => q.status === "approved").length, total: qs.length, panel: !!s.panel, start: first ? { title: first.title, href: first.href } : null };
  });
  return withAbsence({ slug, company: COMPANIES[slug].name, available, docs: availableAnnualReports(slug), titles, stages, families, totals: { questions: total, approved, pending: total - approved } }, await loadAbsenceLedger(slug));
}
