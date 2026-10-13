import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { getRepoRoot } from "@/src/lib/ask-intrinsiciq/paths";
import { COMPANIES } from "@/src/lib/story/companies";
import { QUESTIONS } from "@/src/lib/story/questions";
import { SPECIALISTS } from "@/src/lib/panel/specialists";
import { findQuestion, loadCatalog } from "./catalog";
import { loadExplorer, type Explorer } from "./load-explorer";

const REAL = getRepoRoot();
const slugs = Object.keys(COMPANIES);
const view = (key: string) => JSON.parse(fs.readFileSync(path.join(REAL, "companies", key, "company_memory/ask_intrinsiciq/company_research_view.json"), "utf8"));
afterEach(() => { vi.unstubAllEnvs(); vi.resetModules(); });

describe("the canonical catalog", async () => {
  const cat = await loadCatalog();
  it("is the catalog's 36 questions in 6 families plus the two certified questions the category catalog does not list", () => {
    expect(cat.families.map((f) => f.id)).toEqual(["understand-the-business", "financials", "management", "risks-and-diligence", "committee-view", "investor-panel"]);
    expect(cat.questions).toHaveLength(38);
    expect(cat.questions.filter((q) => !q.inCategoryCatalog).map((q) => q.id).sort()).toEqual(["how-good-is-management", "what-did-management-actually-deliver"]);
    expect(new Set(cat.questions.map((q) => q.id)).size).toBe(38);
  });
  it("matches the dependency registry, plus only the certified question the registry lists as a shadow family", () => {
    const reg = JSON.parse(fs.readFileSync(path.join(REAL, "governance/answer_dependency_registry.json"), "utf8")).questions;
    expect(cat.questions.map((q) => q.id).sort()).toEqual([...Object.keys(reg), "what-did-management-actually-deliver"].sort());
  });
  it("every company's generated catalog view lists the same questions in the same families", () => {
    const flat = (v: { categories: { id: string; questions: { id: string }[] }[] }) => v.categories.map((c) => [c.id, c.questions.map((q) => q.id)]);
    for (const s of slugs.slice(1)) expect(flat(view(COMPANIES[s].key)), s).toEqual(flat(view(COMPANIES[slugs[0]].key)));
  });
  it("each question says what it draws on and how it is produced", () => {
    for (const q of cat.questions) { expect(q.title.endsWith("?"), q.id).toBe(true); expect(q.basis).toBeTruthy(); }
    expect(cat.questions.filter((q) => q.drawsOn.length).length).toBeGreaterThan(30);
  });
  it("the five certified questions are reachable from the catalog exactly once each (four directly, one as the vetted successor)", () => {
    const certs = cat.questions.map((q) => q.certifiedId).filter(Boolean) as string[];
    expect(certs.sort()).toEqual(QUESTIONS.map((q) => q.id as string).sort());
    expect(cat.questions.find((q) => q.id === "what-can-break-the-thesis")!.certifiedId).toBe("what-could-go-wrong");
    // an answer that covers FY20–FY26 does not answer "what was delivered in the last three years": no alias
    expect(cat.questions.find((q) => q.id === "what-was-delivered-last-3-years")!.certifiedId).toBeNull();
    expect(findQuestion(cat, "what-did-management-actually-deliver")).toMatchObject({ viaCertified: false });
    expect(findQuestion(cat, "what-could-go-wrong")?.viaCertified).toBe(true);
    expect(findQuestion(cat, "not-a-question")).toBeNull();
  });
  it("specialist mappings use catalog ids; the 15 proposed questions are NOT in the catalog", () => {
    const ids = new Set(cat.questions.map((q) => q.id));
    for (const s of SPECIALISTS) { for (const q of s.questions) expect(ids.has(q.id), `${s.id}/${q.id}`).toBe(true); for (const p of s.proposed) expect(ids.has(p.id), p.id).toBe(false); }
    expect(SPECIALISTS.flatMap((s) => s.proposed)).toHaveLength(15);
    expect(cat.questions.find((q) => q.id === "how-is-capital-allocated")!.specialists.length).toBeGreaterThanOrEqual(2);
  });
});

describe("every company can browse every question; availability is decided per company-question pair", async () => {
  const ex: Record<string, Explorer> = Object.fromEntries(await Promise.all(slugs.map(async (s) => [s, (await loadExplorer(s))!])));
  it("all 38 questions are discoverable for all four companies, in the same families", () => {
    for (const s of slugs) {
      expect(ex[s].families.flatMap((f) => f.questions)).toHaveLength(38);
      expect(ex[s].families.map((f) => f.id)).toEqual(ex[slugs[0]].families.map((f) => f.id));
    }
  });
  it("availability is exactly the approval registry (M59.4: 91 approved pairs, 61 pending, 152 in all); the five certified questions stay available for every company", () => {
    const registry = Object.keys(JSON.parse(fs.readFileSync(path.join(REAL, "governance/approval_registry.json"), "utf8")).approvals);
    let approved = 0, pending = 0;
    for (const s of slugs) {
      const key = COMPANIES[s].key;
      const ok = ex[s].families.flatMap((f) => f.questions).filter((q) => q.status === "approved").map((q) => q.certifiedId ?? q.id);
      expect(new Set(ok), s).toEqual(new Set(registry.filter((k) => k.startsWith(`${key}:`)).map((k) => k.split(":")[1])));   // nothing is approved that the registry does not list, and vice versa
      for (const q of QUESTIONS) expect(ok, `${s}/${q.id}`).toContain(q.id as string);
      approved += ex[s].totals.approved; pending += ex[s].totals.pending;
    }
    expect([approved, pending, approved + pending]).toEqual([91, 61, 152]);
    expect(registry).toHaveLength(91);
  });
  it("a pending question links to its own page; an approved one to its certified answer", () => {
    const q = ex["sun-pharma"].families.flatMap((f) => f.questions);
    expect(q.find((x) => x.id === "what-evidence-would-change-the-view")).toMatchObject({ status: "pending", href: "/company/sun-pharma/question/what-evidence-would-change-the-view" });   // deferred in M59: still pending
    expect(q.find((x) => x.id === "what-can-break-the-thesis")).toMatchObject({ status: "approved", href: "/company/sun-pharma/question/what-could-go-wrong" });
  });
});

// A throw-away repository root: companies/ and governance files are links to the real data, except the registry (and
// optionally one company's answers file) which the test may change. The real files are never written.
function fixture(edit: { registry?: (r: any) => void; hybrid?: { company: string; edit: (h: any) => void } }) { // eslint-disable-line @typescript-eslint/no-explicit-any
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "m58-"));
  fs.mkdirSync(path.join(root, "governance"));
  const reg = JSON.parse(fs.readFileSync(path.join(REAL, "governance/approval_registry.json"), "utf8"));
  // baseline for these boundary tests: only the five originally certified answers are registered, so each test can add or remove one record
  const CERT = new Set(QUESTIONS.map((q) => q.id as string));
  reg.approvals = Object.fromEntries(Object.entries(reg.approvals).filter(([k]) => CERT.has(k.split(":")[1])));
  edit.registry?.(reg);
  fs.writeFileSync(path.join(root, "governance/approval_registry.json"), JSON.stringify(reg));
  fs.symlinkSync(path.join(REAL, "governance/answer_dependency_registry.json"), path.join(root, "governance/answer_dependency_registry.json"));
  if (!edit.hybrid) fs.symlinkSync(path.join(REAL, "companies"), path.join(root, "companies"));
  else {
    const c = edit.hybrid.company;
    const mirror = (rel: string, except?: string) => { fs.mkdirSync(path.join(root, rel), { recursive: true }); for (const f of fs.readdirSync(path.join(REAL, rel))) if (f !== except) fs.symlinkSync(path.join(REAL, rel, f), path.join(root, rel, f)); };
    mirror("companies", c); mirror(`companies/${c}`, "company_memory"); mirror(`companies/${c}/company_memory`, "ask_intrinsiciq"); mirror(`companies/${c}/company_memory/ask_intrinsiciq`, "shadow_level3_hybrid_answers.json");
    const rel = `companies/${c}/company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json`;
    const h = JSON.parse(fs.readFileSync(path.join(REAL, rel), "utf8"));
    edit.hybrid.edit(h);
    fs.writeFileSync(path.join(root, rel), JSON.stringify(h));
  }
  return root;
}
async function load(root: string) {
  vi.resetModules(); vi.stubEnv("ASK_INTRINSICIQ_REPO_ROOT", root);
  const [e, q, a] = await Promise.all([import("./load-explorer"), import("@/src/lib/story/load-question"), import("@/src/lib/ask-intrinsiciq/load-answer-card")]);
  return { explorer: e.loadExplorer, view: q.loadQuestionView, a };
}
const approvedIds = (e: Awaited<ReturnType<typeof loadExplorer>>) => e!.families.flatMap((f) => f.questions).filter((q) => q.status === "approved").map((q) => q.certifiedId ?? q.id);

describe("certification boundaries hold: listing a question never makes its answer available", () => {
  it("revoked approvals fail closed, for that company only", async () => {
    const m = await load(fixture({ registry: (r) => { r.approvals["sun_pharma:how-is-capital-allocated"].status = "REVOKED"; } }));
    expect(approvedIds((await m.explorer("sun-pharma"))!)).not.toContain("how-is-capital-allocated");
    expect(await m.view("sun-pharma", "how-is-capital-allocated")).toBeNull();
    expect(approvedIds((await m.explorer("tanla"))!)).toContain("how-is-capital-allocated");
  });
  it("edited answers (digest mismatch) fail closed", async () => {
    const m = await load(fixture({ hybrid: { company: "ujjivan", edit: (h) => { h.answers["what-could-go-wrong"].answer.simple_answer += " (edited)"; } } }));
    expect(approvedIds((await m.explorer("ujjivan"))!)).not.toContain("what-could-go-wrong");
    expect(await m.view("ujjivan", "what-could-go-wrong")).toBeNull();
    expect(approvedIds((await m.explorer("ujjivan"))!)).toHaveLength(4);
  });
  it("unregistered answers stay unavailable even though an answer artifact exists", async () => {
    const m = await load(fixture({ registry: (r) => { delete r.approvals["datapatterns:what-has-management-promised"]; } }));
    expect(approvedIds((await m.explorer("datapatterns"))!)).not.toContain("what-has-management-promised");
    const real = JSON.parse(fs.readFileSync(path.join(REAL, "companies/sun_pharma/company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json"), "utf8")).answers;
    expect(real["did-execution-lead-to-outcomes"].status).toBe("PASS"); // a complete, valid-looking artifact...
    expect(await m.view("sun-pharma", "did-execution-lead-to-outcomes")).toBeNull(); // ...is still not served: it was never approved
    expect(await m.view("sun-pharma", "which-investments-created-value")).toBeNull();
  });
  it("another company's answer cannot be substituted", async () => {
    const m = await load(fixture({ hybrid: { company: "tanla", edit: (h) => { h.company_slug = "sun_pharma"; } } }));
    expect(approvedIds((await m.explorer("tanla"))!)).toEqual([]);
    expect(await m.view("tanla", "how-good-is-management")).toBeNull();
  });
  it("a question registered for one company is not available for another", async () => {
    const root = fixture({});
    const m0 = await load(root);
    const reg = JSON.parse(fs.readFileSync(path.join(root, "governance/approval_registry.json"), "utf8"));
    const a = JSON.parse(fs.readFileSync(path.join(REAL, "companies/sun_pharma/company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json"), "utf8")).answers["did-execution-lead-to-outcomes"].answer;
    reg.approvals["sun_pharma:did-execution-lead-to-outcomes"] = { fingerprint: m0.a.computeAnswerFingerprint(a), full_artifact_digest: m0.a.computeFullArtifactDigest(a), artifact_identity_version: "2", approved_at: "t", approved_by: "fixture", note: "fixture", company: "sun_pharma", question: "did-execution-lead-to-outcomes" };
    fs.writeFileSync(path.join(root, "governance/approval_registry.json"), JSON.stringify(reg));
    const m = await load(root);
    expect(approvedIds((await m.explorer("sun-pharma"))!)).toContain("did-execution-lead-to-outcomes");
    expect(approvedIds((await m.explorer("tanla"))!)).not.toContain("did-execution-lead-to-outcomes");
    expect(await m.view("tanla", "did-execution-lead-to-outcomes")).toBeNull();
  });
  it("onboarding is ready for certification: a newly registered, valid answer is served by the shared renderer with no code change", async () => {
    const root = fixture({});
    const m0 = await load(root);
    const reg = JSON.parse(fs.readFileSync(path.join(root, "governance/approval_registry.json"), "utf8"));
    const a = JSON.parse(fs.readFileSync(path.join(REAL, "companies/sun_pharma/company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json"), "utf8")).answers["which-investments-created-value"].answer;
    reg.approvals["sun_pharma:which-investments-created-value"] = { fingerprint: m0.a.computeAnswerFingerprint(a), full_artifact_digest: m0.a.computeFullArtifactDigest(a), artifact_identity_version: "2", approved_at: "t", approved_by: "fixture", note: "fixture", company: "sun_pharma", question: "which-investments-created-value" };
    fs.writeFileSync(path.join(root, "governance/approval_registry.json"), JSON.stringify(reg));
    const m = await load(root);
    const v = await m.view("sun-pharma", "which-investments-created-value");
    expect(v?.question).toMatchObject({ id: "which-investments-created-value", title: "Which investments have actually created value?", family: "Management & Progression" });
    expect(v!.conclusion.length).toBeGreaterThan(40);
    expect(JSON.stringify(v)).not.toMatch(/\b[A-Z]{2,4}-\d{3,}\b|\b[A-Z]{3,}_[A-Z_]{3,}\b/); // no internal identifiers
    expect((await m.explorer("sun-pharma"))!.totals.approved).toBe(6);
  });
  it("the five certified answers are unchanged: same ids, same text on the real registry", async () => {
    const m = await load(REAL);
    for (const q of QUESTIONS) for (const s of slugs) expect((await m.view(s, q.id))?.question.id, `${s}/${q.id}`).toBe(q.id);
    expect((await m.view("sun-pharma", "what-has-management-promised"))!.conclusion).toMatch(/46 tracked management statements/);
  });
});
