/**
 * Prometheus UI Integration Closure tests.
 *
 * Validates the three remediated issues:
 *  1. Dead prometheus/adapter removed
 *
 * Plus onboarding-contract and regression checks.
 */

import { existsSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  getCompanySlugs,
  getLandingCompanies,
  getCompanyResearchView,
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
