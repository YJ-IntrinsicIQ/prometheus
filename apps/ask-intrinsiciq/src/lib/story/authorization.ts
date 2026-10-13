import fs from "node:fs";
import path from "node:path";
import { getApprovedHybridCard } from "@/src/lib/ask-intrinsiciq/load-answer-card";
import { getRepoRoot } from "@/src/lib/ask-intrinsiciq/paths";
import { COMPANIES } from "./companies";
import { loadCatalog } from "@/src/lib/catalog/catalog";
import { QUESTIONS } from "./questions";
import { readJsonIfExists } from "@/src/lib/prometheus/read-json";

/**
 * Which investor questions may be shown for a company: exactly those whose stored answer passes the approval gate
 * (approved, unrevoked, fingerprint and digest unchanged, customer text validated). There is no rollout flag and no
 * second system; a revoked or edited answer drops out on the next request.
 */
const TTL_MS = 5000;
const cache = new Map<string, { key: string; at: number; value: string[] }>();

function stamp(slug: string): string {
  const root = getRepoRoot();
  const m = (p: string) => { try { return fs.statSync(p).mtimeMs; } catch { return 0; } };
  return `${m(path.join(root, "governance", "approval_registry.json"))}|${m(path.join(root, "companies", COMPANIES[slug].key, "company_memory", "ask_intrinsiciq", "shadow_level3_hybrid_answers.json"))}`;
}

export async function approvedQuestionIds(slug: string): Promise<string[]> {
  if (!COMPANIES[slug]) return [];
  const key = stamp(slug);
  const hit = cache.get(slug);
  if (hit && hit.key === key && Date.now() - hit.at < TTL_MS) return hit.value;
  // Only questions that are canonical AND carry a registry record can possibly be approved; each is then put through the full gate.
  const [catalog, registry] = await Promise.all([loadCatalog(), readJsonIfExists<{ approvals?: Record<string, unknown> }>(path.join(getRepoRoot(), "governance", "approval_registry.json"))]);
  const canonical = new Set<string>([...QUESTIONS.map((q) => q.id as string), ...catalog.questions.map((q) => q.id), ...catalog.questions.flatMap((q) => (q.certifiedId ? [q.certifiedId] : []))]);
  const candidates = [...canonical].filter((q) => registry?.approvals?.[`${COMPANIES[slug].key}:${q}`]);
  const ok = await Promise.all(candidates.map(async (q) => {
    try { return (await getApprovedHybridCard(slug, q)) ? q : null; } catch { return null; }
  }));
  const value = ok.filter((x): x is string => x !== null);
  cache.set(slug, { key, at: Date.now(), value });
  return value;
}
