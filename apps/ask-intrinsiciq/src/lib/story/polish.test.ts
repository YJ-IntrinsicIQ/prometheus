import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { COMPANIES } from "./companies";
import { loadQuestionView } from "./load-question";
import { loadStory } from "./load-story";
import { QUESTIONS } from "./question-view";

const slugs = Object.keys(COMPANIES);

describe("Cockpit — timeline labels never hide wording", async () => {
  for (const slug of slugs) {
    const story = (await loadStory(slug))!;
    it(`${slug}: every shortened event label keeps its complete original text`, () => {
      for (const e of story.events) {
        if (e.headline.endsWith("…")) {
          expect(e.original, e.headline).toBeTruthy();
          expect(e.original!.startsWith(e.headline.replace(/^(Commitment|Priority): /, "").replace(/…$/, "").trim().slice(0, 30))).toBe(true);
          expect(e.original!.length).toBeGreaterThan(e.headline.length);
        }
        expect(e.headline.length, e.headline).toBeLessThanOrEqual(141);
      }
    });
    it(`${slug}: connection titles are complete (not ellipsised)`, () => {
      for (const c of story.connections) expect(c.title.endsWith("…"), c.title).toBe(false);
    });
  }
});

describe("Cockpit — metric cards", async () => {
  it("values are short, with units kept and supporting text separate", async () => {
    for (const slug of slugs) for (const q of QUESTIONS) {
      const v = (await loadQuestionView(slug, q.id))!;
      for (const f of v.facts) {
        expect(f.value.length, `${slug}/${q.id}/${f.label}`).toBeLessThanOrEqual(34);
        expect(f.value, f.label).not.toMatch(/→|INR|crore|\bfy\d\d\b/);
        expect(f.period, f.label).not.toMatch(/→|\bfy\d\d\b/);
      }
    }
  });
  it("prefers '₹58,462 Cr' with the earlier value as supporting text", async () => {
    const v = (await loadQuestionView("sun-pharma", "how-is-capital-allocated"))!;
    const r = v.facts.find((f) => /^Revenue/.test(f.label))!;
    expect(r.value).toBe("₹58,462 Cr");
    expect(r.note).toBe("up from ₹43,886 Cr in FY23");
  });
});

describe("Cockpit — Tanla status conflict is shown, not silently resolved", async () => {
  it("flags the disagreement and keeps the approved answer unchanged", async () => {
    const v = (await loadQuestionView("tanla", "how-good-is-management"))!;
    expect(v.notices).toHaveLength(1);
    expect(v.notices[0].text).toMatch(/1 of 3 measurable commitments as delayed/);
    expect(v.notices[0].text).toMatch(/do not establish a missed deadline/);
    expect(JSON.stringify(v.drilldown.original)).toMatch(/1 delayed/i); // approved wording preserved
    for (const [slug, q] of [["tanla", "what-has-management-promised"], ["ujjivan", "how-good-is-management"], ["sun-pharma", "how-good-is-management"], ["datapatterns", "how-good-is-management"]])
      expect((await loadQuestionView(slug, q))!.notices).toHaveLength(0);
  });
});

describe("Cockpit — approved intelligence only", () => {
  const read = (dir: string) => readdirSync(dir, { recursive: true, withFileTypes: true }).filter((e) => e.isFile() && /\.tsx?$/.test(e.name) && !e.name.includes(".test.")).map((e) => readFileSync(path.join(e.parentPath, e.name), "utf8"));
  it("no UI or story code reads shadow candidates or V5 regeneration files", () => {
    for (const dir of [path.join(__dirname, "../../../app"), path.join(__dirname, "../../components"), __dirname, path.join(__dirname, "../ask-intrinsiciq")])
      for (const t of read(dir)) expect(t).not.toMatch(/regeneration_candidate|m541[01]_|shadow candidate|CANDIDATE_UNAPPROVED/i);
  });
  it("there is no rollout flag: no feature-flag or canary variables are read by the app", () => {
    for (const t of [...read(path.join(__dirname, "../../../app")), ...read(path.join(__dirname, "../../lib")), ...read(path.join(__dirname, "../../components"))])
      expect(t).not.toMatch(/ENABLE_INVESTMENT_COCKPIT|INVESTMENT_COCKPIT_ALLOW|PROMETHEUS_LEVEL3_UI_CANARY/);
  });
});
