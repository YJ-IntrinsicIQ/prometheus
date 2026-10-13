import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { getRepoRoot } from "@/src/lib/ask-intrinsiciq/paths";
import { loadCatalog } from "@/src/lib/catalog/catalog";
import { COMPANIES } from "@/src/lib/story/companies";
import { QUESTIONS } from "@/src/lib/story/question-view";
import { findCitations } from "@/src/lib/evidence/cite";
import { loadPanel } from "./load-panel";
import { SPECIALISTS } from "./specialists";
import type { Panel } from "./build-panel";

const slugs = Object.keys(COMPANIES);
const COCKPIT = new Set<string>(QUESTIONS.map((q) => q.id));
afterEach(() => { vi.unstubAllEnvs(); vi.resetModules(); });

describe("the five frameworks are distinct and map onto the canonical catalog", async () => {
  const cat = await loadCatalog();
  const catalog = new Set(cat.questions.map((q) => q.id));
  it("five specialists with different core questions and different lenses", () => {
    expect(SPECIALISTS.map((s) => s.id)).toEqual(["graham", "fisher", "buffett", "munger", "lynch"]);
    expect(new Set(SPECIALISTS.map((s) => s.coreQuestion)).size).toBe(5);
    expect(new Set(SPECIALISTS.flatMap((s) => s.evaluates)).size).toBe(SPECIALISTS.flatMap((s) => s.evaluates).length);
  });
  it("every mapped question id is a canonical catalog id; none is duplicated or invented, and each specialist reuses a certified one", () => {
    for (const s of SPECIALISTS) {
      const ids = s.questions.map((q) => q.id);
      expect(new Set(ids).size, s.id).toBe(ids.length);
      for (const id of ids) expect(catalog.has(id), `${s.id}: ${id}`).toBe(true);
      expect(ids.some((id) => cat.questions.find((q) => q.id === id)!.certifiedId), `${s.id} reuses a certified question`).toBe(true);
      const certs = ids.map((id) => cat.questions.find((q) => q.id === id)!.certifiedId).filter(Boolean);
      expect(new Set(certs).size, `${s.id}: one certified answer is not listed twice`).toBe(certs.length);
    }
  });
  it("proposed questions are genuinely missing from the catalog and never collide with existing ids", () => {
    const proposed = SPECIALISTS.flatMap((s) => s.proposed.map((p) => p.id));
    expect(new Set(proposed).size).toBe(proposed.length);
    for (const id of proposed) { expect(catalog.has(id)).toBe(false); expect(COCKPIT.has(id)).toBe(false); }
    for (const s of SPECIALISTS) expect(s.proposed.length).toBeGreaterThanOrEqual(2);
  });
  it("a question may serve several specialists (one answer, several perspectives)", () => {
    const count = new Map<string, number>();
    for (const s of SPECIALISTS) for (const q of s.questions) count.set(q.id, (count.get(q.id) ?? 0) + 1);
    expect(count.get("how-is-capital-allocated")).toBeGreaterThanOrEqual(2);
    expect(count.get("what-did-management-actually-deliver")).toBeGreaterThanOrEqual(2);
    expect(count.get("what-was-delivered-last-3-years")).toBeGreaterThanOrEqual(1); // its own (pending) question, never the whole-record answer
  });
});

describe("the Panel works for every company, from existing evidence only", async () => {
  const panels: Record<string, Panel> = Object.fromEntries(await Promise.all(slugs.map(async (s) => [s, (await loadPanel(s))!])));
  it("five specialist views for each company, each with all five sections' content", () => {
    for (const s of slugs) {
      expect(panels[s].specialists, s).toHaveLength(5);
      for (const v of panels[s].specialists) {
        expect(v.coreQuestion).toBeTruthy();
        expect(v.uncertain.length, `${s}/${v.id}: honest gaps`).toBeGreaterThan(0);
        expect(v.takeaway.length).toBeGreaterThan(60);
        expect(v.questions.length).toBeGreaterThan(4);
        expect(v.lenses.length).toBeGreaterThanOrEqual(6);
        expect(v.openQuestion.length).toBeGreaterThan(10);
      }
    }
  });
  it("Sun Pharma: every specialist has real evidence-backed observations", () => {
    for (const v of panels["sun-pharma"].specialists) expect(v.observations.length, v.id).toBeGreaterThanOrEqual(4);
  });
  it("perspectives are different: no observation is repeated across specialists, and cards open with different content", () => {
    for (const s of slugs) {
      const texts = panels[s].specialists.flatMap((v) => v.observations.map((o) => o.text));
      expect(new Set(texts).size, s).toBe(texts.length);
      const opening = panels[s].specialists.map((v) => v.observations[0]?.text ?? v.id);
      expect(new Set(opening).size, s).toBe(5);
    }
  });
  it("every claim carries a source, and approved-answer claims only exist where the answer is approved", () => {
    for (const s of slugs) for (const v of panels[s].specialists) for (const o of v.observations) {
      expect(o.sources.length, `${s}/${v.id}: ${o.text.slice(0, 50)}`).toBeGreaterThan(0);
      if (o.basis === "Approved answer") for (const q of QUESTIONS.filter((x) => o.sources.some((src) => src.includes(x.title)))) expect(panels[s].available, `${s}: ${q.id}`).toContain(q.id);
      for (const c of findCitations(o.text + o.sources.join(" "))) expect(c.page).toBeGreaterThan(0);
    }
  });
  it("no valuation, rating or recommendation is ever produced; missing price is stated, not filled in", () => {
    for (const s of slugs) {
      const all = panels[s].specialists.flatMap((v) => [...v.observations.map((o) => o.text), v.takeaway]).join(" ");
      expect(all, s).not.toMatch(/\b(undervalued|overvalued|buy|sell|hold rating|target price|price target|intrinsic value of|margin of safety of|fair value of)\b/i);
      expect(all, s).not.toMatch(/\b\d+\s*\/\s*10\b|\bscore of\b|\brating of\b/i);
      const g = panels[s].specialists.find((v) => v.id === "graham")!;
      expect(g.uncertain.some((x) => /No market price/.test(x.text)), s).toBe(true);
      expect(g.takeaway, s).toMatch(/No margin of safety is stated/);
      expect(panels[s].specialists.find((v) => v.id === "lynch")!.uncertain.some((x) => /price is needed/.test(x.text)), s).toBe(true);
      expect(g.lenses.find((l) => l.name === "Market price and valuation")!.available).toBe(false);
    }
  });
  it("implausible stored values never reach an observation (e.g. a 10,000× debt-to-equity, a bank's 1,673 receivable days)", () => {
    const all = panels["ujjivan"].specialists.flatMap((v) => v.observations.map((o) => o.text)).join(" ");
    expect(all).not.toMatch(/10153|26526089|1673|1,673|144003680022/);
  });
  it("a bank is not judged with industrial measures: no owner earnings or debt ratios for Ujjivan", () => {
    const u = panels["ujjivan"].specialists;
    expect(u.flatMap((v) => v.observations).some((o) => /owner earnings ₹|debt-to-equity|cash conversion cycle/.test(o.text))).toBe(false);
    expect(u.find((v) => v.id === "buffett")!.uncertain.some((g) => /bank/.test(g.text))).toBe(true);
  });
  it("sparse companies keep honest gaps: Data Patterns' mixed reporting basis withholds trends instead of guessing", () => {
    const dp = panels["datapatterns"];
    expect(dp.specialists.find((v) => v.id === "fisher")!.uncertain.some((g) => /like for like|multi-year/.test(g.text))).toBe(true);
    expect(dp.specialists.find((v) => v.id === "munger")!.observations.some((o) => /reporting basis/.test(o.text))).toBe(true);
  });
  it("no company's data appears in another's Panel", () => {
    for (const s of slugs.filter((x) => x !== "sun-pharma")) expect(JSON.stringify(panels[s]), s).not.toMatch(/Sun Pharma|Nidlegy|Ilumya|Alchemee|hazardous|Leqselvi/i);
    expect(JSON.stringify(panels["sun-pharma"])).not.toMatch(/Tanla|Ujjivan|Data Patterns|ValueFirst|Gamooga/i);
  });
  it("every mapped question links to the shared page; approved ones to their certified answer", async () => {
    for (const s of slugs) for (const v of panels[s].specialists) for (const q of v.questions) {
      const cq = (await loadCatalog()).questions.find((x) => x.id === q.id)!;
      expect(q.status === "approved", `${s}/${q.id}`).toBe(panels[s].available.includes(cq.certifiedId ?? q.id));
      expect(q.href).toBe(`/company/${s}/question/${q.status === "approved" ? cq.certifiedId ?? q.id : q.id}`); // always resolves to the shared question page
    }
  });
  it("Sun Pharma examples: Buffett separates three earnings measures; Munger carries tracker-versus-evidence; Lynch sizes revenue drivers", () => {
    const by = (id: string) => panels["sun-pharma"].specialists.find((v) => v.id === id)!;
    expect(by("buffett").observations.some((o) => /reported profit ₹11,479 cr; operating cash flow ₹12,419 cr; estimated owner earnings ₹8,810 cr/.test(o.text))).toBe(true);
    expect(by("munger").observations.some((o) => /Tracker versus evidence/.test(o.text))).toBe(true);
    expect(by("lynch").observations.some((o) => /India 33\.8%.*United States of America 30\.3%/.test(o.text))).toBe(true);
    expect(by("fisher").observations.some((o) => /1 target level reported reached, 1 partly evidenced, 1 in progress/.test(o.text))).toBe(true);
  });
});

describe("an answer without approval is never presented as approved", () => {
  it("revoking one approval removes it from the Panel's claims and marks its question 'no approved answer'", async () => {
    const REAL = getRepoRoot();
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "panel-"));
    fs.mkdirSync(path.join(root, "governance"));
    const reg = JSON.parse(fs.readFileSync(path.join(REAL, "governance/approval_registry.json"), "utf8"));
    reg.approvals["sun_pharma:how-is-capital-allocated"].status = "REVOKED";
    fs.writeFileSync(path.join(root, "governance/approval_registry.json"), JSON.stringify(reg));
    fs.symlinkSync(path.join(REAL, "governance/answer_dependency_registry.json"), path.join(root, "governance/answer_dependency_registry.json"));
    fs.symlinkSync(path.join(REAL, "companies"), path.join(root, "companies"));
    fs.symlinkSync(path.join(REAL, "data"), path.join(root, "data"));
    vi.resetModules(); vi.stubEnv("ASK_INTRINSICIQ_REPO_ROOT", root);
    const { loadPanel: load } = await import("./load-panel");
    const p = (await load("sun-pharma"))!;
    expect(p.available).not.toContain("how-is-capital-allocated");
    const flat = p.specialists.flatMap((v) => v.observations);
    expect(flat.some((o) => o.sources.some((s) => /How is capital allocated\?/.test(s)))).toBe(false);
    for (const v of p.specialists) for (const q of v.questions.filter((x) => x.id === "how-is-capital-allocated")) { expect(q.status).toBe("not-approved"); expect(q.href).toBe("/company/sun-pharma/question/how-is-capital-allocated"); }
    expect(p.specialists.find((v) => v.id === "buffett")!.observations.length).toBeGreaterThan(0); // the Panel degrades; it does not fail
  });
});
