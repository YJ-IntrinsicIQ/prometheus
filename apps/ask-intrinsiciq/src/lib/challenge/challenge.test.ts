// M63 challenge runner. Default run: every case must equal its recorded G0 baseline (so a fix or a regression is visible and
// deliberate). CHALLENGE_STRICT=1: every case must PASS (the real acceptance gate). CHALLENGE_WRITE=1 writes preview/ results.
import { createHash } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { getRepoRoot } from "@/src/lib/ask-intrinsiciq/paths";
import { COMPANIES } from "@/src/lib/story/companies";
import { runCase, type Case } from "./engine";
import { renderSurfaces, type Surface } from "./surfaces";

const root = getRepoRoot();
const sha = (s: string | Buffer) => createHash("sha256").update(s).digest("hex");
const file = JSON.parse(readFileSync(path.join(root, "tests/challenge/cases.json"), "utf8"));
const cases: Case[] = file.cases;
const observations: Case[] = file.observations ?? []; // extra findings made while building the instrument; tracked like cases, outside the 25
const baselinePath = path.join(root, "tests/challenge/baseline.json");
const baseline: Record<string, string> = existsSync(baselinePath) ? JSON.parse(readFileSync(baselinePath, "utf8")).status : {};

// Statements that claim something is missing/undisclosed (the class SP-08/09 target). Inventory only; classification is reviewed by hand.
export const NEGATIVE = /not in the records|records? (do(es)? not|don.t) (show|say|contain|include|record)|not disclosed|undisclosed|not (yet )?(available|stated|reported|recorded|extracted|provided)|unavailable|is silent|records are silent|does not (disclose|state|say|report)|do(es)? not disclose|cannot be (determined|tested|measured|verified)|missing (data|disclosure)/i;

describe("M63 challenge cases on the real rendered surfaces", async () => {
  const surfacesBy: Record<string, Surface[]> = {};
  for (const slug of Object.keys(COMPANIES)) surfacesBy[slug] = await renderSurfaces(slug);
  const results = [...cases, ...observations].map((c) => ({ ...runCase(c, surfacesBy), case: c }));

  const state = {
    registry_sha256: sha(readFileSync(path.join(root, "governance/approval_registry.json"))),
    answers_sha256: Object.fromEntries(Object.entries(COMPANIES).map(([s, c]) => [s, sha(readFileSync(path.join(root, "companies", c.key, "company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json")))])),
    surfaces_sha256: sha(JSON.stringify(surfacesBy)),
  };
  const runHash = sha(JSON.stringify({ state, results: results.map((r) => [r.id, r.status, r.results.map((x) => [x.ok, x.evidence])]) }));

  const negatives = Object.entries(surfacesBy).flatMap(([company, surfaces]) =>
    surfaces.flatMap((s) => s.text.split("\n").flatMap((line) => line.split(/(?<=[.;])\s+/).filter((x) => NEGATIVE.test(x)).map((statement) => ({ company, surface: s.name, statement: statement.replace(/\s+/g, " ").trim() })))));

  if (process.env.CHALLENGE_WRITE) {
    writeFileSync(path.join(root, "preview/m63_g0_results.json"), JSON.stringify({ run_hash: runHash, state, results: results.map((r) => ({ id: r.id, pri: r.case.pri, class: r.case.class, control: !!r.case.control, observation: r.id.startsWith("OB-"), predicted: r.case.predicted, status: r.status, expected: r.case.expected, source: r.case.source, results: r.results })) }, null, 1));
    writeFileSync(path.join(root, "preview/m63_g0_negative_claims.json"), JSON.stringify({ count: negatives.length, unique: new Set(negatives.map((n) => n.company + "|" + n.statement)).size, items: negatives }, null, 1));
    writeFileSync(baselinePath, JSON.stringify({ run_hash: runHash, status: Object.fromEntries(results.map((r) => [r.id, r.status])) }, null, 1));
  }

  it("has 25 cases: 12 Sun Pharma + 13 cross-company; 5 controls", () => {
    expect(cases.length).toBe(25);
    expect(cases.filter((c) => c.id.startsWith("SP-")).length).toBe(12);
    expect(cases.filter((c) => c.control).length).toBe(5);
  });
  it.each(results.map((r) => [r.id, r] as const))("%s", (id, r) => {
    const detail = r.results.map((x) => `${x.ok ? "ok " : "BAD"} ${x.company} ${x.check} :: ${x.evidence}`).join("\n");
    if (process.env.CHALLENGE_STRICT) expect(r.status, `${r.case.expected}\n${detail}`).toBe("PASS");
    else expect(r.status, `baseline moved for ${id}\n${detail}`).toBe(baseline[id] ?? r.status);
  });
});
