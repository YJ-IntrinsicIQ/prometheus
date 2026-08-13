import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  loadPrometheusSources,
  getCompanyResearchView,
  getResearchAnswer,
  getResearchQuestionParams,
} from "@/src/lib/prometheus/adapter";
import { buildResearchAnswer } from "@/src/lib/prometheus/answer-builders";
import { containsForbiddenUiTerm } from "@/src/lib/prometheus/sanitizers";

const envRepoRoot = process.env.ASK_INTRINSICIQ_REPO_ROOT;

afterEach(() => {
  if (envRepoRoot === undefined) {
    delete process.env.ASK_INTRINSICIQ_REPO_ROOT;
  } else {
    process.env.ASK_INTRINSICIQ_REPO_ROOT = envRepoRoot;
  }
});

describe("prometheus adapter", () => {
  it("returns a company research view with a development note when synthetic files are incomplete", async () => {
    const repoRoot = await createFixtureRepo();
    process.env.ASK_INTRINSICIQ_REPO_ROOT = repoRoot;

    const company = await getCompanyResearchView("datapatterns");

    expect(company).not.toBeNull();
    expect(company?.slug).toBe("datapatterns");
    expect(company?.categories).toHaveLength(5);
    expect(company?.developmentNote).toMatch(/fallback demo content/i);
  });

  it("does not crash when source files are missing", async () => {
    const repoRoot = await mkdtemp(path.join(tmpdir(), "ask-intrinsiciq-empty-"));
    const loaded = await loadPrometheusSources("datapatterns", repoRoot);

    expect(loaded.status.available).toHaveLength(0);
    expect(loaded.status.missing.length).toBeGreaterThan(0);
  });

  it("keeps forbidden internal terms out of UI-facing sourced answers", async () => {
    const answer = buildResearchAnswer(
      "datapatterns",
      "what-does-company-do",
      {
        pcim: {
          business_understanding: {
            latest_business_view: {
              business_model: {
                business_summary:
                  "PCIM summary from companies/datapatterns/company_memory/pcim_v1.json with evidence_ids ev_alpha.",
                business_model:
                  "This artifact explains the business model without exposing raw JSON or source_chunk terms.",
                characteristics: ["High-reliability systems", "Evidence from source_artifact"],
              },
            },
          },
        },
        truthPack: null,
        ownerEarningsBridge: null,
        workingCapitalQuality: null,
        capitalAllocationRoi: null,
        perShareCompounding: null,
        buffettAnalysis: null,
        grahamAnalysis: null,
        fisherAnalysis: null,
        mungerAnalysis: null,
        lynchAnalysis: null,
        committeeSynthesis: null,
        committeeBriefQa: null,
        panelRunSummary: null,
      },
      null,
    );

    expect(answer).not.toBeNull();

    const texts = [
      answer?.directAnswer,
      answer?.explanation,
      ...(answer?.supportingPoints.map((point) => point.detail) ?? []),
      ...(answer?.supportingEvidence.map((item) => item.detail) ?? []),
      answer?.uncertaintyNote.detail,
    ].filter(Boolean) as string[];

    expect(texts.every((text) => !containsForbiddenUiTerm(text))).toBe(true);
  });

  it("returns non-empty real answers for the four sourced question routes when real files exist", async () => {
    const repoRoot = path.resolve(process.cwd(), "..", "..");
    const loaded = await loadPrometheusSources("datapatterns", repoRoot);

    for (const questionId of [
      "what-does-company-do",
      "are-profits-converting-into-cash",
      "how-is-capital-allocated",
      "what-would-buffett-focus-on",
      "what-are-key-risks",
    ]) {
      const answer = await getResearchAnswer("datapatterns", questionId);
      expect(answer).not.toBeNull();
      expect(answer?.directAnswer.trim().length).toBeGreaterThan(20);
      expect(["sourced", "partially_sourced"]).toContain(answer?.answerStatus);
    }

    expect(loaded.status.available.length).toBeGreaterThan(0);
  });

  it("suppresses generic progression and placeholder uncertainty on the Buffett lens", async () => {
    const answer = await getResearchAnswer("datapatterns", "what-would-buffett-focus-on");

    expect(answer).not.toBeNull();

    const text = JSON.stringify(answer).toLowerCase();
    expect(text).not.toContain("earlier promise");
    expect(text).not.toContain("unspecified");
    expect(text).not.toContain("no material evidence limitation");
    expect(text).not.toContain("source set summaries");
  });

  it(
    "every catalog question has a valid route and exactly three next questions",
    async () => {
      const params = getResearchQuestionParams();

      expect(params.length).toBeGreaterThanOrEqual(25);

      const answers = await Promise.all(
        params.map((param) => getResearchAnswer(param.companySlug, param.questionId)),
      );

      for (const answer of answers) {
        expect(answer).not.toBeNull();
        expect(answer?.nextQuestionIds).toHaveLength(3);
        expect(answer?.nextQuestions).toHaveLength(3);
      }
    },
    15000,
  );

  it("management commitment questions now resolve from canonical commitment evidence", async () => {
    const answer = await getResearchAnswer("datapatterns", "did-past-claims-come-true");

    expect(answer).not.toBeNull();
    expect(["sourced", "partially_sourced"]).toContain(answer?.answerStatus);
    expect(answer?.directAnswer).toMatch(/promise|delivered|commitment/i);
    expect(answer?.nextQuestionIds).toHaveLength(3);
    expect(answer?.whatChanged).toBeDefined();
    expect(answer?.confidence).toBeDefined();
  });

  it("at least one question per category returns sourced or partially sourced content when real files exist", async () => {
    const sourcedQuestions = [
      "what-does-company-do",
      "what-is-owner-earnings",
      "how-is-capital-allocated",
      "what-would-graham-worry-about",
      "which-disclosure-is-missing",
    ] as const;

    for (const questionId of sourcedQuestions) {
      const answer = await getResearchAnswer("datapatterns", questionId);
      expect(answer).not.toBeNull();
      expect(["sourced", "partially_sourced"]).toContain(answer?.answerStatus);
    }
  });

  it("management promise-vs-delivery answers expose commitment progression", async () => {
    const answer = await getResearchAnswer("datapatterns", "did-past-claims-come-true");

    expect(answer).not.toBeNull();
    expect(["sourced", "partially_sourced"]).toContain(answer?.answerStatus);
    expect(answer?.directAnswer).toMatch(/promise|delivery|commitment/i);
    expect(answer?.supportingPoints.length).toBeGreaterThan(0);
    expect(answer?.askDiagnostics?.detectedIntent).toBe("management_commitments");
  });
});

async function createFixtureRepo() {
  const repoRoot = await mkdtemp(path.join(tmpdir(), "ask-intrinsiciq-fixture-"));
  const companyMemoryRoot = path.join(
    repoRoot,
    "companies",
    "datapatterns",
    "company_memory",
  );
  await mkdir(companyMemoryRoot, { recursive: true });
  await writeFile(
    path.join(companyMemoryRoot, "pcim_v1.json"),
    JSON.stringify({
      business_understanding: {
        latest_business_view: {
          business_model: {
            business_summary:
              "The company builds specialized aerospace and defence electronics systems.",
            business_model:
              "It appears to operate through engineered systems and subsystem programs.",
            value_creation:
              "Execution quality matters because customers rely on fit, reliability, and integration.",
            characteristics: [
              "Program-led demand",
              "Specialized manufacturing discipline",
            ],
            competitive_position_summary:
              "The business looks differentiated through specification depth rather than broad scale.",
          },
        },
      },
    }),
  );

  return repoRoot;
}
