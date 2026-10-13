import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { getRepoRoot } from "@/src/lib/ask-intrinsiciq/paths";
import { COMPANIES } from "@/src/lib/story/companies";
import { QUESTIONS } from "@/src/lib/story/questions";

const REAL = getRepoRoot();
const slugs = Object.keys(COMPANIES);
afterEach(() => { vi.unstubAllEnvs(); vi.resetModules(); });
type Entry = { question_id: string; answer: Record<string, unknown>; candidate: { fingerprint: string; full_artifact_digest: string } };
const candidates = (key: string): Record<string, Entry> => JSON.parse(fs.readFileSync(path.join(REAL, "companies", key, "company_memory/ask_intrinsiciq/m59_candidate_answers.json"), "utf8")).answers;

describe("M59 candidates: exact artifacts, never read by the application, activated only through the registry", () => {
  it("candidate files exist for every company, are marked as candidates, and used zero AI calls", () => {
    for (const s of slugs) {
      const doc = JSON.parse(fs.readFileSync(path.join(REAL, "companies", COMPANIES[s].key, "company_memory/ask_intrinsiciq/m59_candidate_answers.json"), "utf8"));
      expect(doc.schema_version).toBe("m59_candidates_v1");
      expect(doc.ai_calls).toBe(0);
      expect(doc.note).toMatch(/CANDIDATES ONLY/);
      expect(Object.keys(doc.answers).length).toBeGreaterThan(10);
    }
  });
  it("no application code reads the candidate files", () => {
    const walk = (d: string): string[] => fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(path.join(d, e.name)) : /\.tsx?$/.test(e.name) && !/\.test\./.test(e.name) ? [path.join(d, e.name)] : []));
    for (const f of [...walk(path.join(REAL, "apps/ask-intrinsiciq/src")), ...walk(path.join(REAL, "apps/ask-intrinsiciq/app"))]) expect(fs.readFileSync(f, "utf8"), f).not.toMatch(/m59_candidate|m59_pairs|m59_3_replacement/);
  });
  it("after M59.4 the real registry serves every candidate at its exact digest, and the ten excluded pairs stay unavailable", async () => {
    const { loadExplorer } = await import("./load-explorer");
    const { loadQuestionView } = await import("@/src/lib/story/load-question");
    const gate = JSON.parse(fs.readFileSync(path.join(REAL, "preview/M59_3_FINAL_AUTHORIZATION_MANIFEST.json"), "utf8"));
    const reg = JSON.parse(fs.readFileSync(path.join(REAL, "governance/approval_registry.json"), "utf8")).approvals;
    expect(Object.keys(reg)).toHaveLength(91);
    for (const e of gate.pairs) expect(reg[`${e.company}:${e.question_id}`]?.full_artifact_digest, `${e.company}/${e.question_id}`).toBe(e.full_artifact_digest);
    for (const s of slugs) {
      const ex = (await loadExplorer(s))!;
      expect(ex.totals.approved, s).toBe(Object.keys(reg).filter((k) => k.startsWith(`${COMPANIES[s].key}:`)).length);
    }
    expect(gate.excluded).toHaveLength(10);
    for (const x of gate.excluded) {
      const s = slugs.find((k) => COMPANIES[k].key === x.company)!;
      expect(await loadQuestionView(s, x.question_id), `${s}/${x.question_id}`).toBeNull();
      expect(reg[`${x.company}:${x.question_id}`]).toBeUndefined();
    }
  });
  it("the six replaced approvals carry the corrected classification and the other fourteen are untouched", () => {
    const gate = JSON.parse(fs.readFileSync(path.join(REAL, "preview/M59_3_FINAL_AUTHORIZATION_MANIFEST.json"), "utf8"));
    const reg = JSON.parse(fs.readFileSync(path.join(REAL, "governance/approval_registry.json"), "utf8")).approvals;
    const replaced = gate.approved_answers_needing_separate_correction;
    expect(replaced).toHaveLength(6);
    for (const r of replaced) expect(reg[`${r.company}:${r.question_id}`].full_artifact_digest, `${r.company}/${r.question_id}`).toBe(r.replacement_digest);
    const originals = ["what-has-management-promised", "what-did-management-actually-deliver", "how-good-is-management", "how-is-capital-allocated", "what-could-go-wrong"];
    const touched = new Set(replaced.map((r: { company: string; question_id: string }) => `${r.company}:${r.question_id}`));
    expect(Object.keys(reg).filter((k) => originals.includes(k.split(":")[1]) && !touched.has(k))).toHaveLength(14);
  });
});

describe("M59.4 closure: every approved link resolves, Story and Connections do not contradict the corrected classification", () => {
  it("each approved explorer entry opens a served answer; no pending entry does", async () => {
    const { loadExplorer } = await import("./load-explorer");
    const { loadQuestionView } = await import("@/src/lib/story/load-question");
    for (const s of slugs) {
      const ex = (await loadExplorer(s))!;
      for (const q of ex.families.flatMap((f) => f.questions)) {
        const v = await loadQuestionView(s, q.certifiedId ?? q.id);
        if (q.status === "approved") { expect(v, `${s}/${q.id}`).toBeTruthy(); expect(q.href, `${s}/${q.id}`).toMatch(new RegExp(`^/company/${s}/question/`)); }
        else expect(v, `${s}/${q.id}`).toBeNull();
      }
    }
  }, 300000);
  it("Story, Connections and Discoveries never call a statement without a target and deadline a hard commitment (Tanla, Ujjivan, Data Patterns)", async () => {
    const { loadStory } = await import("@/src/lib/story/load-story");
    for (const s of ["tanla", "ujjivan", "datapatterns"]) {
      const story = (await loadStory(s))!;
      const t = JSON.stringify([story.connections, story.discoveries, story.accountability ?? null]);
      expect(t, s).not.toMatch(/\d+ hard commitments|hard commitments with a (specific )?target/i);
    }
    const sun = JSON.stringify((await loadStory("sun-pharma"))!.discoveries);
    expect(sun).toMatch(/3 hard/);   // Sun: three commitments with a target and deadline, as verified
  }, 300000);
});

describe("after owner authorization every candidate is served by the shared renderer, and nothing else changes", () => {
  it("registering all candidates' exact digests in a scratch registry serves each one, and the five certified answers are untouched", async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "m59-"));
    fs.mkdirSync(path.join(root, "governance"));
    const reg = JSON.parse(fs.readFileSync(path.join(REAL, "governance/approval_registry.json"), "utf8"));
    fs.symlinkSync(path.join(REAL, "governance/answer_dependency_registry.json"), path.join(root, "governance/answer_dependency_registry.json"));
    const mirror = (rel: string, except?: string) => { fs.mkdirSync(path.join(root, rel), { recursive: true }); for (const f of fs.readdirSync(path.join(REAL, rel))) if (f !== except) fs.symlinkSync(path.join(REAL, rel, f), path.join(root, rel, f)); };
    mirror("companies");
    const total: Record<string, string[]> = {};
    const replaced: string[] = [];
    for (const s of slugs) {
      const key = COMPANIES[s].key, rel = `companies/${key}`;
      fs.rmSync(path.join(root, rel)); mirror(rel, "company_memory"); mirror(`${rel}/company_memory`, "ask_intrinsiciq"); mirror(`${rel}/company_memory/ask_intrinsiciq`, "shadow_level3_hybrid_answers.json");
      const doc = JSON.parse(fs.readFileSync(path.join(REAL, rel, "company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json"), "utf8"));
      total[s] = [];
      for (const [q, e] of Object.entries(candidates(key))) {
        doc.answers[q] = { question_id: q, answer: e.answer, status: "PASS", coverage: "COMPLETE", word_count: 1 };
        reg.approvals[`${key}:${q}`] = { fingerprint: e.candidate.fingerprint, full_artifact_digest: e.candidate.full_artifact_digest, artifact_identity_version: "2", approved_at: "t", approved_by: "scratch", note: "scratch", company: key, question: q };
        total[s].push(q);
      }
      const rp = path.join(REAL, rel, "company_memory/ask_intrinsiciq/m59_3_replacement_candidates.json");
      if (fs.existsSync(rp)) for (const [q, e] of Object.entries(JSON.parse(fs.readFileSync(rp, "utf8")).answers as Record<string, { answer: unknown; replacement: { fingerprint: string; full_artifact_digest: string } }>)) {
        doc.answers[q].answer = e.answer;                                       // controlled reapproval of the six corrected answers
        reg.approvals[`${key}:${q}`] = { ...reg.approvals[`${key}:${q}`], fingerprint: e.replacement.fingerprint, full_artifact_digest: e.replacement.full_artifact_digest };
        replaced.push(`${s}/${q}`);
      }
      fs.writeFileSync(path.join(root, rel, "company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json"), JSON.stringify(doc));
    }
    fs.writeFileSync(path.join(root, "governance/approval_registry.json"), JSON.stringify(reg));
    vi.resetModules(); vi.stubEnv("ASK_INTRINSICIQ_REPO_ROOT", root);
    const { loadExplorer } = await import("./load-explorer");
    const { loadQuestionView } = await import("@/src/lib/story/load-question");
    let served = 0;
    for (const s of slugs) {
      const ex = (await loadExplorer(s))!;
      const approved = ex.families.flatMap((f) => f.questions).filter((q) => q.status === "approved").map((q) => q.certifiedId ?? q.id);
      for (const q of total[s]) {
        expect(approved, `${s}/${q}`).toContain(q);
        const v = await loadQuestionView(s, q);
        expect(v, `${s}/${q} served after registration`).toBeTruthy();
        expect(JSON.stringify(v), `${s}/${q}`).not.toMatch(/\b(?:MC|RG|PJ|CAO)-\d{2,}\b|\b[A-Z]{3,}_[A-Z_]{3,}\b/);
        served++;
      }
      for (const q of QUESTIONS) expect(await loadQuestionView(s, q.id), `${s}/${q.id}`).toBeTruthy(); // the five certified answers still serve
    }
    expect(served).toBeGreaterThanOrEqual(68);
    expect(replaced).toHaveLength(6);
    for (const r of replaced) {                                                  // the six replacements serve, with the corrected classification
      const [s, q] = r.split("/");
      const v = await loadQuestionView(s, q);
      expect(v, r).toBeTruthy();
      expect(JSON.stringify(v), r).toMatch(/verifiable commitment/i);
      expect(JSON.stringify(v), r).not.toMatch(/\d+ hard commitments/i);
    }
  }, 600000);
});

describe("isolation and revocation hold for candidates registered in a scratch registry", () => {
  const scratch = (register: (key: string) => boolean, revoke?: string) => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "m59-iso-"));
    fs.mkdirSync(path.join(root, "governance"));
    const reg = JSON.parse(fs.readFileSync(path.join(REAL, "governance/approval_registry.json"), "utf8"));
    const CERT = new Set(QUESTIONS.map((q) => q.id as string));
    reg.approvals = Object.fromEntries(Object.entries(reg.approvals).filter(([k]) => CERT.has(k.split(":")[1])));   // baseline: the five certified answers only
    fs.symlinkSync(path.join(REAL, "governance/answer_dependency_registry.json"), path.join(root, "governance/answer_dependency_registry.json"));
    const mirror = (rel: string, except?: string) => { fs.mkdirSync(path.join(root, rel), { recursive: true }); for (const f of fs.readdirSync(path.join(REAL, rel))) if (f !== except) fs.symlinkSync(path.join(REAL, rel, f), path.join(root, rel, f)); };
    mirror("companies");
    for (const s of slugs) {
      const key = COMPANIES[s].key, rel = `companies/${key}`;
      fs.rmSync(path.join(root, rel)); mirror(rel, "company_memory"); mirror(`${rel}/company_memory`, "ask_intrinsiciq"); mirror(`${rel}/company_memory/ask_intrinsiciq`, "shadow_level3_hybrid_answers.json");
      const doc = JSON.parse(fs.readFileSync(path.join(REAL, rel, "company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json"), "utf8"));
      if (register(key)) for (const [q, e] of Object.entries(candidates(key))) {
        doc.answers[q] = { question_id: q, answer: e.answer, status: "PASS", coverage: "COMPLETE", word_count: 1 };
        reg.approvals[`${key}:${q}`] = { fingerprint: e.candidate.fingerprint, full_artifact_digest: e.candidate.full_artifact_digest, artifact_identity_version: "2", approved_at: "t", approved_by: "scratch", note: "scratch", company: key, question: q, ...(revoke === `${key}:${q}` ? { status: "REVOKED" } : {}) };
      }
      fs.writeFileSync(path.join(root, rel, "company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json"), JSON.stringify(doc));
    }
    fs.writeFileSync(path.join(root, "governance/approval_registry.json"), JSON.stringify(reg));
    vi.resetModules(); vi.stubEnv("ASK_INTRINSICIQ_REPO_ROOT", root);
  };

  it("registering one company's candidates serves only that company", async () => {
    scratch((k) => k === "sun_pharma");
    const { loadQuestionView } = await import("@/src/lib/story/load-question");
    const sunQs = Object.keys(candidates("sun_pharma"));
    const q = sunQs.find((x) => x in candidates("tanla"))!;
    expect(await loadQuestionView("sun-pharma", q), "registered company serves").toBeTruthy();
    expect(await loadQuestionView("tanla", q), "other company is not served by a neighbour's registration").toBeFalsy();
  }, 120000);

  it("a revoked record withdraws exactly that answer", async () => {
    const q = Object.keys(candidates("sun_pharma"))[0], other = Object.keys(candidates("sun_pharma"))[1];
    scratch((k) => k === "sun_pharma", `sun_pharma:${q}`);
    const { loadQuestionView } = await import("@/src/lib/story/load-question");
    expect(await loadQuestionView("sun-pharma", q), "revoked").toBeFalsy();
    expect(await loadQuestionView("sun-pharma", other), "its neighbour still serves").toBeTruthy();
  }, 120000);
});
