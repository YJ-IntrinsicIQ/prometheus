import { describe, it, expect } from "vitest";
import {
  getCompanySlugs,
  getLandingCompanies,
  getCompanyResearchView,
  getResearchAnswerCard,
} from "@/src/lib/ask-intrinsiciq";

describe("production validation", () => {
  it("all companies discovered with correct availability", async () => {
    const slugs = await getCompanySlugs();
    console.log("Discovered slugs:", slugs.join(", "));
    const companies = await getLandingCompanies();
    for (const c of companies) {
      console.log(`  ${c.slug}: ${c.availabilityState} | ${c.reportingPeriods.join(",") || "none"} | ${c.primaryIndustry?.slice(0, 50)}`);
    }
    // sun_pharma directory maps to public slug "sun-pharma" via generic underscore→hyphen rule.
    expect(slugs).toContain("sun-pharma");
    expect(slugs).toContain("ujjivan");
    expect(slugs).toContain("tanla");
    expect(slugs.length).toBeGreaterThanOrEqual(3);
  });

  it("ujjivan research view loads correctly", async () => {
    const view = await getCompanyResearchView("ujjivan");
    expect(view).not.toBeNull();
    expect(view?.company.companySlug).toBe("ujjivan");
    console.log(`ujjivan: ${view?.company.displayName} | ${view?.sourceState.contentStatus}`);
  });

  it("tanla research view loads correctly", async () => {
    const view = await getCompanyResearchView("tanla");
    expect(view).not.toBeNull();
    expect(view?.company.companySlug).toBe("tanla");
    console.log(`tanla: ${view?.company.displayName} | ${view?.sourceState.contentStatus}`);
  });

  it("Buffett answer card structured sections (check for Gold sections)", async () => {
    for (const slug of ["sun-pharma", "ujjivan", "tanla"]) {
      const card = await getResearchAnswerCard(slug, "what-would-buffett-focus-on");
      const sections = card?.structuredSections ?? [];
      console.log(`  ${slug}: answerStatus=${card?.answerStatus} | sections=[${sections.map(s => s.title).join(", ")}]`);
      // Verify no "(Gold)" in any displayed section title from the card
      for (const section of sections) {
        expect(section.title, `Raw backend title "${section.title}" should not contain "(Gold)" — normalization should strip it`).not.toContain("(Gold)");
      }
    }
  });

  it("newly discovered companies beyond the three audited ones appear automatically", async () => {
    const slugs = await getCompanySlugs();
    const newCompanies = slugs.filter(s => !["sun-pharma", "ujjivan", "tanla"].includes(s));
    console.log("Additional discovered companies:", newCompanies.join(", "));
    // For each extra company, verify a research view loads (may be PARTIAL)
    for (const slug of newCompanies) {
      const view = await getCompanyResearchView(slug);
      expect(view, `${slug} has memory_index but getCompanyResearchView returned null`).not.toBeNull();
      expect(view?.company.companySlug).toBe(slug);
      console.log(`  ${slug}: ${view?.company.displayName} | ${view?.sourceState.contentStatus} | ${view?.sourceState.producer}`);
    }
  });

  it("question route works for a dynamically discovered company", async () => {
    const slugs = await getCompanySlugs();
    // Pick one company not in the audited set
    const testSlug = slugs.find(s => !["sun-pharma", "ujjivan", "tanla"].includes(s)) ?? slugs[0];
    console.log("Testing question route for:", testSlug);
    const answer = await getResearchAnswerCard(testSlug, "what-does-company-do");
    expect(answer).not.toBeNull();
    expect(answer?.questionId).toBe("what-does-company-do");
    console.log(`  ${testSlug}/what-does-company-do: answerStatus=${answer?.answerStatus}`);
  });
});
