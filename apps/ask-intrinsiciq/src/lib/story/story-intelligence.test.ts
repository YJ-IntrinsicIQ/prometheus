import { describe, expect, it } from "vitest";
import { findCitations } from "@/src/lib/evidence/cite";
import { COMPANIES } from "./companies";
import { parseCommitmentEvidence } from "./commitment-evidence";
import { loadQuestionView } from "./load-question";
import { loadStory } from "./load-story";
import { QUESTIONS } from "./question-view";
import { capexProgramme } from "./capital";
import { outcomeEvents } from "./story-events";
import type { Story } from "./story-adapter";

const slugs = Object.keys(COMPANIES);
const CAUSAL = /\b(because of|caused by|led to|resulted in|thanks to|drove|due to)\b/i;

describe("Story draws on more than statements and projects", async () => {
  const stories: Record<string, Story> = Object.fromEntries(await Promise.all(slugs.map(async (s) => [s, (await loadStory(s))!])));
  it("every company has strategy, investment/outcome and risk developments where the records have them", () => {
    for (const s of slugs) {
      const cats = new Set(stories[s].events.map((e) => e.category));
      expect(cats.has("Strategy"), s).toBe(true);
      expect(cats.has("Risk"), s).toBe(true);
      expect(cats.has("Outcome") || cats.has("Investment"), s).toBe(true);
    }
    expect(new Set(stories["sun-pharma"].events.map((e) => e.category)).size).toBeGreaterThanOrEqual(4);
  });
  it("keeps the timeline selective, ordered and bounded", () => {
    for (const s of slugs) {
      const ev = stories[s].events;
      expect(ev.length, s).toBeLessThanOrEqual(22);
      expect(ev.map((e) => e.sortKey)).toEqual([...ev.map((e) => e.sortKey)].sort((a, b) => a - b));
      expect(ev.filter((e) => e.initial).length).toBeLessThanOrEqual(8);
      for (const e of ev) { expect(e.evidence.length, e.headline).toBeGreaterThan(0); expect(new Set(ev.map((x) => x.id)).size).toBe(ev.length); }
    }
  });
  it("connects events only through an explicit tie, and both ends exist", () => {
    for (const s of slugs) {
      const ids = new Set(stories[s].events.map((e) => e.id));
      for (const e of stories[s].events) for (const r of e.related) {
        expect(ids.has(r.id), `${s}: ${e.headline} → ${r.label}`).toBe(true);
        expect(stories[s].events.find((x) => x.id === r.id)!.related.some((b) => b.id === e.id), "ties are mutual").toBe(true);
      }
    }
    expect(stories["sun-pharma"].events.filter((e) => e.related.length).length).toBeGreaterThanOrEqual(6); // 3 commitments × promise ↔ progress
  });
  it("makes no causal claim in text this layer writes, and never calls a missing disclosure a miss", () => {
    for (const s of slugs) {
      const written = stories[s].events.flatMap((e) => [e.interpretation.matters, e.interpretation.unproven]);
      expect(JSON.stringify(written).replace(/do not show what drove/g, ""), s).not.toMatch(CAUSAL); // the disclaimer itself is allowed
      expect(JSON.stringify(stories[s].events.map((e) => e.summary)), s).not.toMatch(/\bmissed\b(?!\.)/i);
    }
  });
  it("an acquisition or capex programme is reported as an action, never as an economic success", () => {
    for (const s of slugs) for (const e of stories[s].events.filter((x) => x.category === "Investment")) {
      expect(`${e.headline} ${e.summary}`).not.toMatch(/\b(success|value created|paid off|accretive|returns? of)\b/i);
      expect(e.interpretation.unproven.length).toBeGreaterThan(20);
    }
  });
});

describe("commitment consistency: tracker status and evidence stay apart", async () => {
  const sun = (await loadStory("sun-pharma"))!;
  it("Sun Pharma: three hard commitments, each with reported evidence, tracker still unable to verify", () => {
    const hard = sun.commitments!.filter((r) => r.hard);
    expect(hard).toHaveLength(3);
    for (const r of hard) {
      expect(r.states.tracker).toBe("Unable to verify");
      expect(r.hasEvidence).toBe(true);
      expect(r.states.economic).toMatch(/None confirmed/);
    }
    const by = (re: RegExp) => hard.find((r) => re.test(r.promise))!;
    expect(by(/hazardous/).deliveryClass).toBe("reached");
    expect(by(/hazardous/).observed.map((o) => o.value)).toEqual([28.34, 47, 59.9]);
    expect(by(/hazardous/).states.target).toMatch(/Reached: 47% in FY25/);
    expect(by(/Nidlegy/).deliveryClass).toBe("partly");
    expect(by(/Nidlegy/).states.target).toMatch(/not established/i);
    expect(by(/carbon/).deliveryClass).toBe("in_progress");
    expect(by(/carbon/).states.target).toMatch(/Not yet reached: 16\.7% in FY26 against 35%/);
    expect(sun.commitments!.filter((r) => !r.hard)).toHaveLength(2);
  });
  it("Sun Pharma: a flat 'unable to verify' is not shown as the whole truth, and a missing result is not a failure", () => {
    const text = JSON.stringify(sun.events.filter((e) => e.commitment));
    expect(text).toMatch(/Reported 28\.34%/);
    expect(text).not.toMatch(/\bmissed\b|\bfailed\b/i);
    expect(sun.discoveries[0].headline).toMatch(/Progress is disclosed on all 3 hard commitments, even though the tracker shows none verified/);
  });
  it("commitment evidence is read only from approved answers: no answer, no rows", () => {
    expect(parseCommitmentEvidence(null, null)).toEqual([]);
    expect(parseCommitmentEvidence({ deterministic_precision_facts: ["46 statements"] }, null)).toEqual([]);
  });
  it("the same rows reach the Promises and Delivery question pages", async () => {
    for (const q of ["what-has-management-promised", "what-did-management-actually-deliver"]) {
      const v = (await loadQuestionView("sun-pharma", q))!;
      const b = v.blocks.find((x) => x.body.kind === "commitments");
      expect(b, q).toBeTruthy();
    }
  });
  it("other companies: a promise with no later evidence is shown as unverified, with no invented progress", async () => {
    for (const s of ["tanla", "ujjivan", "datapatterns"]) {
      const story = (await loadStory(s))!;
      const c = story.events.filter((e) => e.commitment);
      expect(c.length, s).toBeGreaterThan(0);
      for (const e of c) {
        expect(e.commitment!.economic, s).toMatch(/Not established|None confirmed/);
        if (!e.commitment!.execution.match(/\d/)) expect(e.category, `${s}: ${e.headline}`).toBe("Strategy"); // no "execution" event without evidence
      }
    }
  });
});

describe("discoveries and connections are explainable", async () => {
  for (const s of slugs) {
    it(`${s}: every discovery cites its evidence; every connection edge is graded; citations name a year and a page or none`, async () => {
      const st = (await loadStory(s))!;
      expect(st.discoveries.length).toBeGreaterThan(0);
      for (const d of st.discoveries) {
        expect(d.evidence.length, d.headline).toBeGreaterThan(0);
        for (const e of d.evidence) expect(e.source.length).toBeGreaterThan(0);
        expect(d.unknown.length, d.headline).toBeGreaterThan(0);
        expect(`${d.discovered} ${d.significance}`).not.toMatch(CAUSAL);
      }
      for (const c of st.connections) {
        expect(c.edges).toHaveLength(c.nodes.length - 1);
        for (const e of c.edges) expect(["Supported", "Related", "Unverified"]).toContain(e.relation);
        expect(JSON.stringify(c.nodes.flatMap((n) => n.facts))).not.toMatch(CAUSAL);
      }
      // every linkable citation points at a filing that exists
      const all = JSON.stringify([st.events, st.connections, st.discoveries]);
      for (const c of findCitations(all.replace(/\\"/g, '"'))) expect(c.page).toBeGreaterThan(0);
    });
  }
  it("a strong edge is never given to acquisitions or capital-to-project chains", async () => {
    const sun = (await loadStory("sun-pharma"))!;
    expect(sun.connections.filter((c) => c.edges.some((e) => e.relation === "Supported") && c.nodes[0].title === "What management said")).toHaveLength(3);
    for (const c of sun.connections.filter((x) => x.nodes[0].title === "Transactions completed" || x.title.startsWith("Capital spent"))) expect(c.edges.every((e) => e.relation !== "Supported")).toBe(true);
  });
});

describe("financial developments compare only like with like", () => {
  const mk = (xs: [string, number, string][]) => xs.map(([year, value, basis]) => ({ year, value, basis }));
  it("does not compare across a change of basis, or across a gap", () => {
    const e = outcomeEvents(mk([["fy22", 3206, "consolidated"], ["fy25", 4028, "consolidated"], ["fy26", 4418, "consolidated"]]), []);
    expect(e).toHaveLength(1);
    expect(e[0].headline).toMatch(/FY26 reported results: revenue ₹4,418 cr \(up 10% on FY25\)/);
    const unknown = outcomeEvents(mk([["fy24", 520, "unknown"], ["fy25", 708, "standalone"], ["fy26", 925, "unknown"]]), []);
    expect(unknown[0].headline).not.toMatch(/\bup \d+%/);
    expect(unknown[0].limitations.join(" ")).toMatch(/basis not (yet )?(stated|identified)/i);
  });
  it("summarises a long same-basis run once, with arithmetic only", () => {
    const e = outcomeEvents(mk([["fy20", 100, "consolidated"], ["fy21", 110, "consolidated"], ["fy22", 120, "consolidated"], ["fy23", 150, "consolidated"]]), []);
    expect(e[0].headline).toBe("Revenue moved from ₹100 cr (FY20) to ₹150 cr (FY23)");
    expect(e[0].interpretation.unproven).toMatch(/do not attribute this growth/);
  });
  it("capex programme needs an amount over several years", () => {
    expect(capexProgramme([{ action_type: "organic_capex", deployment_state: "DEPLOYED", amount_inr_cr: 50, deployment_periods: ["fy25"] }])).toBeNull();
    expect(capexProgramme([{ action_type: "organic_capex", deployment_state: "DEPLOYED", amount_inr_cr: 50, deployment_periods: ["fy24", "fy25"] }])?.label).toBe("₹50 cr across FY24–FY25");
  });
});

describe("no company data leaks into another", async () => {
  it("Sun-only subjects never appear in the other companies' Story, Connections or Discoveries", async () => {
    for (const s of slugs.filter((x) => x !== "sun-pharma")) {
      const st = await loadStory(s);
      expect(JSON.stringify(st), s).not.toMatch(/Sun Pharma|Nidlegy|Ilumya|Alchemee|Concert Pharma|hazardous waste/i);
    }
    for (const q of QUESTIONS) expect(await loadQuestionView("tanla", q.id)).toBeTruthy();
  });
});
