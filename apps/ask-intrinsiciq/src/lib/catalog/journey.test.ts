import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { getRepoRoot } from "@/src/lib/ask-intrinsiciq/paths";
import { containsForbiddenUiTerm } from "@/src/lib/prometheus/sanitizers";
import { cleanPublicText } from "@/src/lib/ask-intrinsiciq/presentation";
import { COMPANIES } from "@/src/lib/story/companies";
import { loadQuestionView } from "@/src/lib/story/load-question";
import { evidencePeriod, plain, previewText } from "@/src/lib/story/question-view";
import { loadCatalog } from "./catalog";
import { JOURNEY, NEXT, nextInline, relatedFor, servedId, stageOfFamily, VETTED_ALIASES } from "./journey";
import { loadExplorer } from "./load-explorer";

const REAL = getRepoRoot();
const slugs = Object.keys(COMPANIES);
const registry = Object.keys(JSON.parse(fs.readFileSync(path.join(REAL, "governance/approval_registry.json"), "utf8")).approvals);
const approvedFor = (slug: string) => registry.filter((k) => k.startsWith(`${COMPANIES[slug].key}:`)).map((k) => k.split(":")[1]);
const NAMES = Object.fromEntries(slugs.map((s) => [s, COMPANIES[s].name]));

describe("the research journey is built on the existing catalog", async () => {
  const cat = await loadCatalog();
  it("every catalog family belongs to a journey stage, in the investor's order", () => {
    expect(JOURNEY.map((s) => s.id)).toEqual(["understand", "financials", "management", "risks", "frameworks"]);
    for (const f of cat.families) expect(stageOfFamily(f.id), f.id).toBeTruthy();
  });
  it("every progression names questions that exist in the catalog (by catalog id or serving id) and never points at itself", () => {
    const ids = new Set(cat.questions.flatMap((q) => [q.id, servedId(q)]));
    for (const [from, tos] of Object.entries(NEXT)) {
      expect(ids.has(from), from).toBe(true);
      for (const [to] of tos) { expect(ids.has(to), `${from} -> ${to}`).toBe(true); expect(VETTED_ALIASES[to] ?? to, from).not.toBe(VETTED_ALIASES[from] ?? from); }
    }
  });
});

describe.each(slugs)("%s: discoverability and navigation", (slug) => {
  it("every approved pair is accessible and every unavailable pair stays protected", async () => {
    const ex = (await loadExplorer(slug))!;
    const approved = approvedFor(slug);
    expect(ex.totals.approved).toBe(approved.length);
    expect(ex.totals.approved + ex.totals.pending).toBe(ex.totals.questions);
    for (const f of ex.families) for (const q of f.questions) {
      const v = await loadQuestionView(slug, q.status === "approved" ? servedId(q) : q.id);
      if (q.status === "approved") { expect(v, `${slug}/${q.id}`).toBeTruthy(); expect(approved).toContain(servedId(q)); } else expect(v, `${slug}/${q.id}`).toBeNull();
    }
  }, 300000);

  it("approved questions come first in each area, and only they carry a preview taken from their own approved answer", async () => {
    const ex = (await loadExplorer(slug))!;
    const hybrid = JSON.parse(fs.readFileSync(path.join(REAL, "companies", COMPANIES[slug].key, "company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json"), "utf8")).answers;
    for (const f of ex.families) {
      const order = f.questions.map((q) => q.status);
      expect(order, f.id).toEqual([...order].sort((a, b) => (a === b ? 0 : a === "approved" ? -1 : 1)));
      for (const q of f.questions) {
        if (q.status === "pending") { expect(q.preview, `${slug}/${q.id}`).toBeUndefined(); continue; }
        expect(q.preview, `${slug}/${q.id}`).toBeTruthy();
        expect(containsForbiddenUiTerm(q.preview!)).toBe(false);
        expect(q.preview).toBe(previewText(hybrid[servedId(q)].answer));               // derived from the approved answer's own field, nothing added
        const words = (t: string) => new Set(plain(t).toLowerCase().replace(/…$/, "").match(/[a-z0-9₹%.]+/g) ?? []);
        const source = words(String(hybrid[servedId(q)].answer.simple_answer));
        for (const w of words(q.preview!)) expect(source.has(w), `${slug}/${q.id}: "${w}" is not in the approved answer`).toBe(true);
      }
    }
  });

  it("every related-question, next-step and panel link resolves, and nothing names another company", async () => {
    const ex = (await loadExplorer(slug))!;
    const others = slugs.filter((s) => s !== slug).map((s) => NAMES[s]);
    for (const id of ex.available) {
      const v = (await loadQuestionView(slug, id))!;
      for (const r of v.related ?? []) {
        expect(r.href).toBe(`/company/${slug}/question/${r.id}`);
        expect(ex.available, `${slug}/${id} -> ${r.id}`).toContain(r.id);
        expect(await loadQuestionView(slug, r.id), `${slug}/${id} -> ${r.id}`).toBeTruthy();
        expect(r.id).not.toBe(id);
      }
      if (v.next) expect(v.next.href.startsWith(`/company/${slug}/`)).toBe(true);
      for (const p of v.panels ?? []) expect(p.href).toMatch(new RegExp(`^/company/${slug}/panel/(graham|fisher|buffett|munger|lynch)$`));
      const blob = JSON.stringify([v.related, v.next, v.panels, v.titles, v.context]);
      for (const o of others) expect(blob, `${slug}/${id}`).not.toContain(o);
    }
  }, 300000);

  it("inline related links on Story and Connections cards offer only approved questions", async () => {
    const ex = (await loadExplorer(slug))!;
    for (const id of ex.available) for (const x of nextInline(id, ex.available, ex.titles, 3)) { expect(ex.available).toContain(x.id); expect(ex.titles[x.id]).toBeTruthy(); }
    for (const t of Object.keys(ex.titles)) expect(ex.available).toContain(t);   // titles exist for approved questions only
  });
});

describe("displayed text keeps the sanitizer's protections", () => {
  it("no approved answer reaches the page with internal vocabulary, and the sanitizer still blocks unsafe text", async () => {
    for (const slug of slugs) {
      const ex = (await loadExplorer(slug))!;
      for (const id of ex.available) {
        const v = (await loadQuestionView(slug, id))!;
        const shown = JSON.stringify([v.conclusion, v.takeaway, v.facts, v.drilldown.facts, v.drilldown.observations, v.drilldown.limitations, v.drilldown.monitor, v.related]);
        expect(shown, `${slug}/${id}`).not.toMatch(/canonical/i);
        expect(containsForbiddenUiTerm(v.conclusion), `${slug}/${id}`).toBe(false);
      }
    }
    for (const bad of ["see evidence_ids", "stored in companies/sun_pharma/x", "the JSON file", "LLM output", "data pipeline", "Model validation step"]) expect(containsForbiddenUiTerm(bad), bad).toBe(true);
    expect(plain("No canonical confirmation. Canonical status remains open.")).toBe("No confirmation. Status remains open.");
  }, 300000);
});

describe("the M59.4 sanitizer warnings concern the legacy card projection, not what the Cockpit shows", () => {
  it("fields the legacy cleaner blanks are shown in full on the page, unchanged except for internal vocabulary", async () => {
    // legacy cleaner: "act on; it does not show…" trips its preposition-then-semicolon truncation guard although the sentence is complete
    const answer = JSON.parse(fs.readFileSync(path.join(REAL, "companies/sun_pharma/company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json"), "utf8")).answers["what-was-delivered-last-3-years"].answer;
    expect(cleanPublicText(answer.what_may_mean_economically)).toBe("");
    const v = (await loadQuestionView("sun-pharma", "what-was-delivered-last-3-years"))!;
    expect(v.takeaway).toContain("it does not show what the delivery earned");
    // the cleaner's real protections are untouched
    expect(cleanPublicText("See the data pipeline for the source artifact.")).toBe("");
    expect(cleanPublicText("Revenue grew in; margins")).toBe("");
  });
});

describe("filing evidence is kept apart from as-of dates and deadlines", () => {
  const ujjivanDocs = ["fy21", "fy22", "fy23", "fy24", "fy25"];
  it("a year beyond the latest annual report held is labelled as an as-of date, not as evidence", () => {
    const r = evidencePeriod("9 more centres by FY 2025-26; the FY25 report cites 23. Made in FY22; confirmed as of FY26.", ujjivanDocs);
    expect(r.period).toBe("FY22–FY25");
    expect(r.note).toMatch(/FY26 appears only as an as-of date or a deadline.*FY25/);
  });
  it("a company whose latest report covers the year keeps it as evidence (Sun Pharma FY26)", () => {
    expect(evidencePeriod("FY20–FY26 revenue", ["fy20", "fy26"])).toEqual({ period: "FY20–FY26", note: "" });
  });
  it("Ujjivan pages never present FY26 as filing evidence", async () => {
    const ex = (await loadExplorer("ujjivan"))!;
    for (const id of ex.available) {
      const v = (await loadQuestionView("ujjivan", id))!;
      expect(v.period, id).not.toMatch(/FY26/);
      for (const f of v.facts) expect(f.period, `${id}/${f.label}`).not.toBe("FY26");
    }
  }, 300000);
});

describe("related questions follow the research, not the alphabet", async () => {
  const cat = await loadCatalog();
  const all = Object.values(cat.questions).map(servedId);
  it("a promise leads to its delivery, and profit leads to owner earnings", () => {
    expect(relatedFor(cat, all, "sun-pharma", "what-has-management-promised")[0].id).toBe("what-did-management-actually-deliver");
    expect(relatedFor(cat, all, "sun-pharma", "are-profits-converting-into-cash")[0].id).toBe("what-is-owner-earnings");
    expect(relatedFor(cat, all, "sun-pharma", "how-is-capital-allocated").map((r) => r.id)).toContain("which-investments-created-value");
  });
  it("an unavailable question is never suggested", () => {
    const only = ["what-has-management-promised"];
    expect(relatedFor(cat, only, "tanla", "what-has-management-promised")).toEqual([]);
  });
});
