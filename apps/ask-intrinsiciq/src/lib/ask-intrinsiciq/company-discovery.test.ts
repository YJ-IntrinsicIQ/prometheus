import { describe, expect, it } from "vitest";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { tmpdir } from "node:os";
import {
  getCompanyResearchView,
  getLandingCompanies,
  getResearchAnswerCard,
  getCompanySlugs,
} from "@/src/lib/ask-intrinsiciq";

async function writeJson(filePath: string, payload: unknown) {
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, JSON.stringify(payload), "utf8");
}

describe("company discovery", () => {
  it("discovers the target companies without collapsing them into a single demo company", async () => {
    const slugs = await getCompanySlugs();

    expect(slugs).toEqual(
      expect.arrayContaining(["datapatterns", "tanla", "tips", "polymatech"]),
    );
    expect(slugs).not.toContain("acme");
  });

  it("returns landing entries with per-company availability and summary data", async () => {
    const companies = await getLandingCompanies();

    expect(companies.length).toBeGreaterThanOrEqual(4);
    expect(companies.map((company) => company.slug)).toEqual(
      expect.arrayContaining(["datapatterns", "tanla", "tips", "polymatech"]),
    );
    companies.forEach((company) => {
      expect(["READY", "PARTIAL", "UNAVAILABLE"]).toContain(company.availabilityState);
      expect(company.summary.length).toBeGreaterThan(0);
    });
  });

  it("keeps company memory isolated per slug", async () => {
    const [tanla, tips, polymatech] = await Promise.all([
      getCompanyResearchView("tanla"),
      getCompanyResearchView("tips"),
      getCompanyResearchView("polymatech"),
    ]);

    expect(tanla?.company.companySlug).toBe("tanla");
    expect(tips?.company.companySlug).toBe("tips");
    expect(polymatech?.company.companySlug).toBe("polymatech");
    expect(tips?.company.shortDescription.toLowerCase()).toContain("music");
    expect(polymatech?.company.shortDescription.toLowerCase()).toContain("manufacturer");
    expect(tanla?.company.shortDescription).not.toEqual(tips?.company.shortDescription);
  });

  it("returns an answer card or a safe unavailable state for a known company question", async () => {
    const answer = await getResearchAnswerCard("tips", "what-does-company-do");

    expect(answer).not.toBeNull();
    expect(answer?.questionId).toBe("what-does-company-do");
    expect(answer?.title).toMatch(/what does the company do/i);
  });

  it("normalizes revenue-flow steps into displayable objects for the make-money answer", async () => {
    for (const companySlug of ["tanla", "datapatterns", "tips", "polymatech"]) {
      const answer = await getResearchAnswerCard(companySlug, "how-does-it-make-money");

      expect(answer).not.toBeNull();
      expect(answer?.questionId).toBe("how-does-it-make-money");
      expect(answer?.revenueFlow?.steps.length).toBeGreaterThan(0);
      expect(
        answer?.revenueFlow?.steps.every(
          (step) => typeof step.label === "string" && typeof step.explanation === "string",
        ),
      ).toBe(true);
    }
  });

  it("rejects mismatched company-specific answer artifacts instead of using wrong-company facts", async () => {
    const originalRepoRoot = process.env.ASK_INTRINSICIQ_REPO_ROOT;
    const repoRoot = await mkdtemp(path.join(tmpdir(), "ask-company-mismatch-"));
    process.env.ASK_INTRINSICIQ_REPO_ROOT = repoRoot;

    try {
      await writeJson(
        path.join(repoRoot, "companies/tanla/company_memory/company_memory_index.json"),
        { company: "tanla", usable_years: ["fy26"], incomplete_years: [] },
      );
      await writeJson(
        path.join(repoRoot, "companies/tanla/company_memory/yearly_intelligence_index.json"),
        {
          company: "tanla",
          years: [
            {
              year: "fy26",
              sort_key: 26,
              status: "usable",
            },
          ],
        },
      );
      await writeJson(
        path.join(repoRoot, "companies/tanla/fy26/intelligence/company_intelligence.json"),
        {
          metadata: { company: "tanla", year: "fy26" },
          business: {
            industry_profile: {
              business_summary:
                "Tanla operates enterprise messaging and communications platforms for telecom operators and enterprise customers.",
            },
          },
        },
      );
      await writeJson(
        path.join(repoRoot, "companies/tanla/company_memory/ask_intrinsiciq/answer_cards.json"),
        {
          company_slug: "datapatterns",
          answers: [
            {
              id: "wrong-company-answer",
              question_id: "what-does-company-do",
              title: "What does the company do?",
              simple_answer: "Data Patterns defence electronics answer.",
              key_points: ["Defence integrator"],
              detailed_explanation: "Wrong company factual answer.",
              products_and_services_refs: [],
              financial_visual_refs: [],
              evidence_summary: {
                status: "direct",
                summary: "Wrong company evidence.",
                supporting_points: [],
              },
              uncertainty_note: { title: "Wrong", message: "Wrong" },
              next_questions: [
                {
                  category_id: "understand-the-business",
                  question_id: "who-are-the-customers",
                  title: "Who are the customers?",
                },
                {
                  category_id: "understand-the-business",
                  question_id: "how-does-it-make-money",
                  title: "How does it make money?",
                },
                {
                  category_id: "management",
                  question_id: "what-has-management-promised",
                  title: "What has management promised?",
                },
              ],
              answer_status: "supported",
              generated_at: "2026-08-13T00:00:00Z",
            },
          ],
        },
      );

      const answer = await getResearchAnswerCard("tanla", "what-does-company-do");

      expect(answer?.answerStatus).toBe("unavailable");
      expect(answer?.simpleAnswer).toMatch(/not complete yet/i);
      expect(JSON.stringify(answer).toLowerCase()).not.toContain("defence integrator");
    } finally {
      if (originalRepoRoot === undefined) {
        delete process.env.ASK_INTRINSICIQ_REPO_ROOT;
      } else {
        process.env.ASK_INTRINSICIQ_REPO_ROOT = originalRepoRoot;
      }
    }
  });
});
