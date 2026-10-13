import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { getRepoRoot } from "@/src/lib/ask-intrinsiciq/paths";
import { COMPANIES } from "./companies";
import { loadQuestionView } from "./load-question";
import { loadStory } from "./load-story";
import { QUESTIONS } from "./question-view";

const root = getRepoRoot();
const LEAK = /\b[A-Z]{2,4}-\d{3,}\b|\b[A-Z]{3,}_[A-Z_]{3,}\b|\b[Rr][Ii][Ss][Kk]_[0-9a-fA-F]{4,}|\b[A-Z]{3,}_\d{3,}|_[0-9a-f]{12}/;
const SUN_ONLY = /Sun Pharma|Nidlegy|Ilumya|Leqselvi|Unloxcyt|Alchemee|Concert Pharma|Organon|Maduranthakam|MKM/;
const CAUSAL = /\b(because of|caused by|led to|resulted in|thanks to|drove)\b/i;
const others = Object.keys(COMPANIES).filter((s) => s !== "sun-pharma");
// Periods the company actually has source documents for (its own fyNN folders).
const years = (key: string) =>
  new Set<number>(readdirSync(path.join(root, "companies", key)).filter((d) => /^fy\d{2}$/.test(d)).map((d) => Number(d.slice(2))));

describe.each(Object.keys(COMPANIES))("cross-company — %s", async (slug) => {
  const key = COMPANIES[slug].key;
  const story = (await loadStory(slug))!;
  const views = await Promise.all(QUESTIONS.map((q) => loadQuestionView(slug, q.id)));
  const reg = JSON.parse(readFileSync(path.join(root, "governance/approval_registry.json"), "utf8"));
  const approvals = reg.approvals ?? reg;

  it("loads Story and all five approved question pages", () => {
    expect(story.company).toBe(COMPANIES[slug].name);
    views.forEach((v, i) => {
      expect(v, QUESTIONS[i].id).toBeTruthy();
      expect(approvals[`${key}:${QUESTIONS[i].id}`], `${key}:${QUESTIONS[i].id}`).toBeTruthy();
      expect(v!.conclusion.length).toBeGreaterThan(40);
      expect(v!.conclusion.length).toBeLessThan(420); // summary stays short
      expect(v!.facts.length).toBeGreaterThanOrEqual(2);
      expect(v!.facts.length).toBeLessThanOrEqual(5);
    });
  });
  it("leaks no identifiers or machine codes; no causal wording in presentation text", () => {
    expect(JSON.stringify(story)).not.toMatch(LEAK);
    for (const v of views) {
      expect(JSON.stringify(v), v!.question.id).not.toMatch(LEAK);
      expect(JSON.stringify([v!.blocks, v!.discoveries])).not.toMatch(CAUSAL);
    }
    // Only text this presentation layer writes (management's own quoted words are excluded).
    const written = [story.events.map((e) => e.interpretation.matters), story.connections.flatMap((c) => c.edges.map((e) => e.note)), story.discoveries.map((d) => [d.why, d.significance])];
    expect(JSON.stringify(written)).not.toMatch(CAUSAL);
  });
  it("every displayed fact appears in the company's own stored answer", () => {
    for (const v of views) {
      const stored = JSON.stringify(JSON.parse(readFileSync(path.join(root, "companies", key, "company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json"), "utf8")).answers[v!.question.id].answer);
      for (const f of v!.facts) {
        const num = /\d[\d,.]*/.exec(f.value)?.[0];
        if (num && v!.question.id !== "what-could-go-wrong") expect(stored.includes(num), `${v!.question.id}: ${f.label}=${f.value}`).toBe(true);
      }
    }
  });
  it("annual-report references use only periods the company actually has", () => {
    const ok = years(key);
    const refs = JSON.stringify([story, views.map((v) => v!.blocks), views.map((v) => v!.discoveries)]).match(/Annual report FY(\d{2})/g) ?? [];
    for (const r of refs) expect(ok.has(Number(r.slice(-2))), `${slug}: ${r}`).toBe(true);
  });
  it("discovery periods stay inside the company's own evidence years", () => {
    const ok = years(key);
    for (const d of story.discoveries) for (const m of d.years.matchAll(/FY(\d{2})/g)) expect(ok.has(Number(m[1])), `${slug}: ${d.headline} ${d.years}`).toBe(true);
  });
  it("shows incomplete chains honestly; only approved records are used; commitment counts add up", () => {
    expect(JSON.stringify(story)).not.toMatch(/[Ss]hadow|unapproved/);
    if (story.accountability) expect(Object.values(story.accountability.counts).reduce((x, y) => x + y, 0)).toBe(story.accountability.total);
    expect(story.accountability === undefined).toBe(COMPANIES[slug].withholdCommitmentRegister === true);
    for (const c of story.connections) expect(c.edges).toHaveLength(c.nodes.length - 1);
    const reg = Object.keys(JSON.parse(readFileSync(path.join(root, "governance/approval_registry.json"), "utf8")).approvals).filter((k) => k.startsWith(`${key}:`));
    expect(story.available).toHaveLength(reg.length);   // M59.4: exactly the pairs the registry lists for this company
    for (const q of QUESTIONS) expect(story.available).toContain(q.id as string);
  });
});

describe("no cross-company leakage", async () => {
  it.each(others)("%s shows no Sun Pharma content", async (slug) => {
    const story = await loadStory(slug);
    const views = await Promise.all(QUESTIONS.map((q) => loadQuestionView(slug, q.id)));
    expect(JSON.stringify([story, views])).not.toMatch(SUN_ONLY);
  });
});
