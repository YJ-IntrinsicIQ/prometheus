/**
 * Prometheus UI Integration Closure tests.
 *
 * Validates the three remediated issues:
 *  1. Dead prometheus/adapter removed
 *  2. Gold-derived section titles normalized before display
 *  3. dynamicParams explicitly declared on dynamic company routes
 *
 * Plus onboarding-contract and regression checks.
 */

import { existsSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { StructuredAnswerSections } from "@/src/components/structured-answer-sections";
import {
  dynamicParams as companyDynamicParams,
} from "@/app/company/[companySlug]/page";
import {
  dynamicParams as questionDynamicParams,
} from "@/app/company/[companySlug]/question/[questionId]/page";
import {
  getCompanySlugs,
  getLandingCompanies,
  getCompanyResearchView,
  getResearchAnswerCard,
} from "@/src/lib/ask-intrinsiciq";

// ── T1: dead adapter deleted ───────────────────────────────────────────────
describe("T1 – dead prometheus/adapter removed", () => {
  it("adapter.ts no longer exists on disk", () => {
    // Resolve from app root (CWD when vitest runs is apps/ask-intrinsiciq)
    const adapterPath = path.resolve("src/lib/prometheus/adapter.ts");
    expect(existsSync(adapterPath)).toBe(false);
  });

  it("adapter.test.ts no longer exists on disk", () => {
    const adapterTestPath = path.resolve("src/lib/prometheus/adapter.test.ts");
    expect(existsSync(adapterTestPath)).toBe(false);
  });
});

// ── T2: canonical dynamic discovery still works ────────────────────────────
describe("T2 – canonical dynamic discovery", () => {
  it("getCompanySlugs() returns at least 3 companies from filesystem", async () => {
    const slugs = await getCompanySlugs();
    expect(slugs.length).toBeGreaterThanOrEqual(3);
  });

  it("getLandingCompanies() returns entries with READY/PARTIAL/UNAVAILABLE states", async () => {
    const companies = await getLandingCompanies();
    expect(companies.length).toBeGreaterThan(0);
    companies.forEach((company) => {
      expect(["READY", "PARTIAL", "UNAVAILABLE"]).toContain(company.availabilityState);
    });
  });
});

// ── T3: dynamicParams explicitly declared ──────────────────────────────────
describe("T3 – dynamicParams explicit declaration", () => {
  it("company [companySlug] page exports dynamicParams = true", () => {
    expect(companyDynamicParams).toBe(true);
  });

  it("question [questionId] page exports dynamicParams = true", () => {
    expect(questionDynamicParams).toBe(true);
  });
});

// ── T4: arbitrary slug resolves through generic route ─────────────────────
describe("T4 – arbitrary discovered slug", () => {
  it("every slug returned by getCompanySlugs() loads a research view", async () => {
    const slugs = await getCompanySlugs();
    const views = await Promise.all(slugs.map((slug) => getCompanyResearchView(slug)));
    views.forEach((view, i) => {
      expect(view, `slug ${slugs[i]} returned null research view`).not.toBeNull();
      expect(view?.company.companySlug).toBe(slugs[i]);
    });
  });
});

// ── T5: new company requires no frontend source modification ───────────────
describe("T5 – no production hardcoded company list", () => {
  it("getLandingCompanies() is driven by filesystem discovery, not a static list", async () => {
    // If discovery were static, adding a new dir+index would not change the list.
    // We verify the list matches exactly what getCompanySlugs() returns — same source of truth.
    const [slugs, companies] = await Promise.all([getCompanySlugs(), getLandingCompanies()]);
    const companySlugs = companies.map((c) => c.slug).sort();
    expect(companySlugs).toEqual([...slugs].sort());
  });
});

// ── T6–T8: Gold section title normalization ────────────────────────────────
describe("T6–T8 – Gold section normalization in StructuredAnswerSections", () => {
  const goldSections = [
    {
      title: "Management track record (Gold)",
      points: ["Consistent delivery on stated targets across three fiscal cycles."],
    },
    {
      title: "Capital deployment returns (Gold)",
      points: ["Incremental ROCE on deployed capital has been positive and above cost."],
    },
  ];

  it("T6 – '(Gold)' suffix is not shown in management track record heading", () => {
    render(<StructuredAnswerSections sections={goldSections} />);
    expect(screen.getByText("Management track record")).toBeInTheDocument();
    expect(screen.queryByText(/\(Gold\)/)).toBeNull();
  });

  it("T7 – '(Gold)' suffix is not shown in capital deployment returns heading", () => {
    render(<StructuredAnswerSections sections={goldSections} />);
    expect(screen.getByText("Capital deployment returns")).toBeInTheDocument();
    expect(screen.queryByText(/\(Gold\)/)).toBeNull();
  });

  it("T8 – normalized Gold sections receive a named style treatment (not default fallback)", () => {
    render(<StructuredAnswerSections sections={goldSections} />);
    // The styled eyebrows "Management" and "Capital allocation" are only rendered
    // when SECTION_STYLES has an entry for the normalized key.
    expect(screen.getByText("Management")).toBeInTheDocument();
    expect(screen.getByText("Capital allocation")).toBeInTheDocument();
  });
});

// ── T9: unknown structured section renders gracefully ──────────────────────
describe("T9 – unknown section renders without crash", () => {
  it("an unrecognized section title gets the default fallback style", () => {
    const sections = [
      { title: "Some future backend section", points: ["A data point."] },
    ];
    render(<StructuredAnswerSections sections={sections} />);
    // Default eyebrow text for unrecognized keys
    expect(screen.getByText("Structured view")).toBeInTheDocument();
    expect(screen.getByText("Some future backend section")).toBeInTheDocument();
  });
});

// ── T10: missing optional artifact does not crash ─────────────────────────
describe("T10 – missing artifact degrades gracefully", () => {
  it("getResearchAnswerCard returns a safe unavailable card, not null, when answer card artifact is absent", async () => {
    // tanla has a company_memory_index but may not have every answer card present.
    const answer = await getResearchAnswerCard("tanla", "what-does-company-do");
    // Must be non-null (graceful unavailable) or fully sourced — never a thrown exception.
    expect(answer).not.toBeNull();
    expect(["unavailable", "sourced", "partially_sourced", "supported"]).toContain(answer?.answerStatus);
  });
});

// ── T11: READY / PARTIAL / UNAVAILABLE states unchanged ───────────────────
describe("T11 – availability states", () => {
  it("at least one company is READY or PARTIAL after all changes", async () => {
    const companies = await getLandingCompanies();
    const nonUnavailable = companies.filter((c) => c.availabilityState !== "UNAVAILABLE");
    expect(nonUnavailable.length).toBeGreaterThan(0);
  });
});

// ── T12: no production hardcoded company list ─────────────────────────────
describe("T12 – production code contains no hardcoded company list", () => {
  it("adapter.ts (which gated on a hardcoded datapatterns check) is gone", () => {
    expect(existsSync(path.resolve("src/lib/prometheus/adapter.ts"))).toBe(false);
  });

  it("discovery-critical files do not contain any company name as a literal string condition", async () => {
    // Load the source of the two authoritative discovery files and verify
    // they contain no literal slug names that would gate discovery.
    const { readFile } = await import("node:fs/promises");
    const [discoverySource, loaderSource] = await Promise.all([
      readFile(path.resolve("src/lib/ask-intrinsiciq/company-discovery.ts"), "utf8"),
      readFile(path.resolve("src/lib/ask-intrinsiciq/load-company-research-view.ts"), "utf8"),
    ]);
    // None of the production company slugs should appear as literal gate conditions
    for (const slug of ["sun_pharma", "ujjivan", "tanla", "sun-pharma"]) {
      // Allow the slug in comments or error messages, but not as a conditional
      const gatedOccurrences = [...discoverySource.matchAll(new RegExp(`=== ?["']${slug}["']`, "g"))];
      expect(gatedOccurrences, `${slug} appears as a literal gate in company-discovery.ts`).toHaveLength(0);
      const gatedInLoader = [...loaderSource.matchAll(new RegExp(`=== ?["']${slug}["']`, "g"))];
      expect(gatedInLoader, `${slug} appears as a literal gate in load-company-research-view.ts`).toHaveLength(0);
    }
  });
});
