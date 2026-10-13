import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { getRepoRoot } from "@/src/lib/ask-intrinsiciq/paths";
import { COMPANIES } from "./companies";
import { QUESTIONS } from "./question-view";

const REAL = getRepoRoot();
const slugs = Object.keys(COMPANIES);
afterEach(() => { vi.unstubAllEnvs(); vi.resetModules(); });

// A throw-away repository root whose companies/ are symlinks to the real data, with a copy of the registry (and
// optionally one company's hybrid answers file) that the test may alter. The real files are never written.
function fixture(opts: { registry?: (r: any) => void; hybrid?: { company: string; edit: (h: any) => void } }) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cockpit-"));
  fs.mkdirSync(path.join(root, "governance"));
  const reg = JSON.parse(fs.readFileSync(path.join(REAL, "governance/approval_registry.json"), "utf8"));
  opts.registry?.(reg);
  fs.writeFileSync(path.join(root, "governance/approval_registry.json"), JSON.stringify(reg));
  fs.symlinkSync(path.join(REAL, "governance/answer_dependency_registry.json"), path.join(root, "governance/answer_dependency_registry.json"));
  const real = path.join(REAL, "companies");
  if (!opts.hybrid) fs.symlinkSync(real, path.join(root, "companies"));
  else {
    // Dirent.isDirectory() is false for a symlink, so companies/ and the edited company are real directories of links.
    const c = opts.hybrid.company;
    const mirror = (rel: string, except?: string) => {
      fs.mkdirSync(path.join(root, rel), { recursive: true });
      for (const f of fs.readdirSync(path.join(REAL, rel))) if (f !== except) fs.symlinkSync(path.join(REAL, rel, f), path.join(root, rel, f));
    };
    mirror("companies", c);
    mirror(`companies/${c}`, "company_memory");
    mirror(`companies/${c}/company_memory`, "ask_intrinsiciq");
    mirror(`companies/${c}/company_memory/ask_intrinsiciq`, "shadow_level3_hybrid_answers.json");
    const rel = `companies/${c}/company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json`;
    const h = JSON.parse(fs.readFileSync(path.join(REAL, rel), "utf8"));
    opts.hybrid.edit(h);
    fs.writeFileSync(path.join(root, rel), JSON.stringify(h));
  }
  return root;
}

async function load(root: string) {
  vi.resetModules();
  vi.stubEnv("ASK_INTRINSICIQ_REPO_ROOT", root);
  const [auth, q, s] = await Promise.all([import("./authorization"), import("./load-question"), import("./load-story")]);
  return { approved: auth.approvedQuestionIds, question: q.loadQuestionView, story: s.loadStory };
}

// M59.4: 91 approved pairs; per-company expectations are read from the registry rather than assumed
const registryFor = (slug: string): string[] => {
  const reg = JSON.parse(fs.readFileSync(path.join(REAL, "governance/approval_registry.json"), "utf8")).approvals as Record<string, unknown>;
  const key = slug === "sun-pharma" ? "sun_pharma" : slug;
  return Object.keys(reg).filter((k) => k.startsWith(`${key}:`)).map((k) => k.split(":")[1]);
};

describe("approval is the only switch", () => {
  it("all four companies serve exactly their registered questions, always including the five certified ones, with no flags or canary settings", async () => {
    for (const k of Object.keys(process.env)) expect(k).not.toMatch(/COCKPIT|CANARY/);
    const m = await load(REAL);
    for (const slug of slugs) {
      const got = (await m.approved(slug)).sort();
      expect(got, slug).toEqual(registryFor(slug).sort());
      for (const q of QUESTIONS) expect(got, `${slug}/${q.id}`).toContain(q.id as string);
      expect(await m.story(slug), slug).toBeTruthy();
    }
  });
  it("a revoked approval drops exactly that question, for that company only; its page and links disappear", async () => {
    const m = await load(fixture({ registry: (r) => { r.approvals["sun_pharma:how-good-is-management"].status = "REVOKED"; } }));
    expect(await m.approved("sun-pharma")).not.toContain("how-good-is-management");
    expect((await m.approved("sun-pharma")).length).toBe(registryFor("sun-pharma").length - 1);
    expect(await m.approved("tanla")).toHaveLength(registryFor("tanla").length);
    expect(await m.question("sun-pharma", "how-good-is-management")).toBeNull();
    const story = (await m.story("sun-pharma"))!;
    expect(story.available).not.toContain("how-good-is-management");
    expect(JSON.stringify([story.connections, story.discoveries])).not.toContain("/question/how-good-is-management");
  });
  it("a changed answer (digest no longer matches its approval) is not shown", async () => {
    const m = await load(fixture({ hybrid: { company: "tanla", edit: (h) => { h.answers["how-is-capital-allocated"].answer.simple_answer += " (edited)"; } } }));
    expect(await m.question("tanla", "how-is-capital-allocated")).toBeNull();
    expect(await m.approved("tanla")).toHaveLength(registryFor("tanla").length - 1);
  });
  it("an unregistered answer is not shown", async () => {
    const m = await load(fixture({ registry: (r) => { delete r.approvals["ujjivan:what-could-go-wrong"]; } }));
    expect(await m.question("ujjivan", "what-could-go-wrong")).toBeNull();
  });
  it("an answer file that belongs to another company is rejected, never used", async () => {
    const m = await load(fixture({ hybrid: { company: "tanla", edit: (h) => { h.company_slug = "sun_pharma"; } } }));
    expect(await m.approved("tanla")).toEqual([]);
    expect(await m.question("tanla", "how-good-is-management")).toBeNull();
  });
});

describe("sparse or missing intelligence is shown honestly", () => {
  it("a company with no approved answers still gets a Story and says so; nothing is borrowed from Sun Pharma", async () => {
    const m = await load(fixture({ registry: (r) => { for (const k of Object.keys(r.approvals)) if (k.startsWith("datapatterns:")) delete r.approvals[k]; } }));
    const story = (await m.story("datapatterns"))!;
    expect(story.available).toEqual([]);
    expect(JSON.stringify(story)).not.toMatch(/Sun Pharma|Nidlegy|Ilumya/);
    for (const q of QUESTIONS) expect(await m.question("datapatterns", q.id)).toBeNull();
  });
  it("unknown companies and unknown questions return nothing", async () => {
    const m = await load(REAL);
    expect(await m.story("acme")).toBeNull();
    expect(await m.question("sun-pharma", "no-such-question")).toBeNull();
  });
});
