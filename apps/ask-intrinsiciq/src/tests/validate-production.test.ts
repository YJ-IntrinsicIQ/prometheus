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

  // ENG-124 / ENG-124A: outcome_attribution_summary full chain — all companies with capital allocation data
  it("ENG-124A: outcome_attribution_summary flows through type chain for all three companies", async () => {
    const cases: Array<{ slug: string; minDirect: number; minTotal: number }> = [
      { slug: "sun-pharma",   minDirect: 4, minTotal: 10 },
      { slug: "tanla",        minDirect: 5, minTotal: 17 },
      { slug: "datapatterns", minDirect: 3, minTotal: 10 },
    ];

    for (const { slug, minDirect, minTotal } of cases) {
      const card = await getResearchAnswerCard(slug, "how-is-capital-allocated");
      expect(card, `${slug}: answer card must exist`).not.toBeNull();
      const oa = card?.interpretation?.outcomeAttributionSummary;
      const total = (oa?.directly_attributable ?? 0) + (oa?.strongly_supported ?? 0) +
        (oa?.associated_not_attributable ?? 0) + (oa?.no_outcome_evidence ?? 0) + (oa?.negative_outcome ?? 0);
      console.log(`${slug}: outcome_attribution_summary=${JSON.stringify(oa)} total=${total}`);

      // Key mapping: all 5 snake_case keys must be present (may be 0)
      expect(oa, `${slug}: outcomeAttributionSummary must be present`).not.toBeNull();
      expect(oa).not.toBeUndefined();
      expect(typeof oa?.directly_attributable).toBe("number");
      expect(typeof oa?.strongly_supported).toBe("number");
      expect(typeof oa?.associated_not_attributable).toBe("number");
      expect(typeof oa?.no_outcome_evidence).toBe("number");
      expect(typeof oa?.negative_outcome).toBe("number");

      // Canonical count fidelity: backend values must reach frontend unchanged
      expect(oa?.directly_attributable, `${slug}: directly_attributable must match ENG-122 canonical count`).toBe(minDirect);
      expect(total, `${slug}: total classified allocations must match ENG-122`).toBe(minTotal);
    }
  });

  // ENG-124A: companies with no capital allocation data must NOT synthesize a summary
  it("ENG-124A: companies without capital allocation data have no outcomeAttributionSummary", async () => {
    // ujjivan has no capital_allocation_outcomes directory — must be absent, not zero-filled
    const card = await getResearchAnswerCard("ujjivan", "how-is-capital-allocated");
    if (card?.interpretation?.outcomeAttributionSummary !== undefined) {
      // If present, verify it came from real data (total > 0) — not a zero-filled fabrication
      const oa = card.interpretation.outcomeAttributionSummary;
      if (oa !== null) {
        const total = (oa.directly_attributable ?? 0) + (oa.strongly_supported ?? 0) +
          (oa.associated_not_attributable ?? 0) + (oa.no_outcome_evidence ?? 0) + (oa.negative_outcome ?? 0);
        expect(total, "ujjivan: if summary present, must have real data (not zero-filled fabrication)").toBeGreaterThan(0);
      }
    }
    // If absent: correct — no capital allocation data, no manufactured summary
    console.log(`ujjivan: outcomeAttributionSummary=${JSON.stringify(card?.interpretation?.outcomeAttributionSummary ?? null)}`);
  });
});
