import path from "node:path";
import { readJsonIfExists } from "@/src/lib/prometheus/read-json";
import { getRepoRoot } from "@/src/lib/ask-intrinsiciq/paths";
import { approvalGate } from "./approval-gate";
import { approvedQuestionIds } from "./authorization";
import { COMPANIES } from "./companies";

type Obj = Record<string, unknown>;

/**
 * The company's approved answers, by question id: only those that pass the approval gate (and the runtime text
 * validation in approvedQuestionIds). Anything unapproved, changed or revoked is simply absent.
 */
export async function loadApprovedAnswers(slug: string, opts: { repoRoot?: string } = {}): Promise<Record<string, Obj>> {
  const company = COMPANIES[slug];
  if (!company) return {};
  const root = opts.repoRoot ?? getRepoRoot();
  const [hybrid, registry, available] = await Promise.all([
    readJsonIfExists<{ company_slug?: string; answers?: Record<string, { status?: string; coverage?: string; answer?: Obj }> }>(path.join(root, "companies", company.key, "company_memory", "ask_intrinsiciq", "shadow_level3_hybrid_answers.json")),
    readJsonIfExists<{ approvals?: Record<string, Obj> }>(path.join(root, "governance", "approval_registry.json")),
    approvedQuestionIds(slug),
  ]);
  if (hybrid?.company_slug && hybrid.company_slug !== company.key) return {};
  const out: Record<string, Obj> = {};
  for (const q of available) {
    const entry = hybrid?.answers?.[q];
    if (entry?.answer && approvalGate(entry, registry?.approvals?.[`${company.key}:${q}`] as never).ok) out[q] = entry.answer;
  }
  return out;
}
