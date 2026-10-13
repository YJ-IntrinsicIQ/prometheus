/**
 * Prometheus Company Slug Contract tests.
 *
 * Validates the generic internalKey ↔ publicSlug separation:
 *   - Underscore directory names map to hyphenated public slugs
 *   - Reverse resolution is exact and collision-safe
 *   - All loaders and route generators use the public slug
 *   - Cross-company contamination guards still hold
 *   - Zero company-specific frontend logic
 */

import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  getDiscoveredCompanySlugs,
  resolveInternalKey,
  getCompanyDiscoverySummary,
} from "@/src/lib/ask-intrinsiciq/company-discovery";
import {
  getCompanySlugs,
  getLandingCompanies,
  getCompanyResearchView,
  getApprovedHybridCard,
} from "@/src/lib/ask-intrinsiciq";

// ── SC1: slug derivation rule ─────────────────────────────────────────────────
describe("SC1 – slug derivation: underscore → hyphen", () => {
  it("getDiscoveredCompanySlugs includes sun-pharma (not sun_pharma)", async () => {
    const slugs = await getDiscoveredCompanySlugs();
    expect(slugs).toContain("sun-pharma");
    expect(slugs).not.toContain("sun_pharma");
  });

  it("all returned slugs match the URL-safe pattern /^[a-z0-9-]+$/", async () => {
    const slugs = await getDiscoveredCompanySlugs();
    for (const slug of slugs) {
      expect(slug).toMatch(/^[a-z0-9-]+$/);
    }
  });
});

// ── SC2: reverse resolution ───────────────────────────────────────────────────
describe("SC2 – resolveInternalKey reverse lookup", () => {
  it("resolveInternalKey('sun-pharma') → 'sun_pharma'", async () => {
    const key = await resolveInternalKey("sun-pharma");
    expect(key).toBe("sun_pharma");
  });

  it("resolveInternalKey('ujjivan') → 'ujjivan' (no underscore, key == slug)", async () => {
    const key = await resolveInternalKey("ujjivan");
    expect(key).toBe("ujjivan");
  });

  it("resolveInternalKey('tanla') → 'tanla'", async () => {
    const key = await resolveInternalKey("tanla");
    expect(key).toBe("tanla");
  });

  it("resolveInternalKey for unknown slug returns null", async () => {
    const key = await resolveInternalKey("does-not-exist-xyz");
    expect(key).toBeNull();
  });

  it("resolveInternalKey for the raw underscore key returns null (it is not a public slug)", async () => {
    const key = await resolveInternalKey("sun_pharma");
    expect(key).toBeNull();
  });
});

// ── SC3: discovery summary carries correct identity fields ────────────────────
describe("SC3 – CompanyDiscoverySummary identity fields", () => {
  it("sun-pharma discovery summary has internalKey=sun_pharma and slug=sun-pharma", async () => {
    const summary = await getCompanyDiscoverySummary("sun-pharma");
    expect(summary).not.toBeNull();
    expect(summary?.internalKey).toBe("sun_pharma");
    expect(summary?.slug).toBe("sun-pharma");
  });

  it("ujjivan discovery summary has internalKey=ujjivan and slug=ujjivan", async () => {
    const summary = await getCompanyDiscoverySummary("ujjivan");
    expect(summary?.internalKey).toBe("ujjivan");
    expect(summary?.slug).toBe("ujjivan");
  });
});

// ── SC4: research views load via public slug ──────────────────────────────────
describe("SC4 – research views use public slug", () => {
  it("getCompanyResearchView('sun-pharma') returns a non-null view", async () => {
    const view = await getCompanyResearchView("sun-pharma");
    expect(view).not.toBeNull();
  });

  it("view.company.companySlug is 'sun-pharma' (public slug, not internal key)", async () => {
    const view = await getCompanyResearchView("sun-pharma");
    expect(view?.company.companySlug).toBe("sun-pharma");
  });

  it("getCompanyResearchView with raw internal key 'sun_pharma' returns null (invalid route segment)", async () => {
    const view = await getCompanyResearchView("sun_pharma");
    expect(view).toBeNull();
  });
});

// ── SC5: approved answers load via public slug ───────────────────────────────
describe("SC5 – approved answers use public slug", () => {
  it("getApprovedHybridCard('sun-pharma', ...) returns the approved card", async () => {
    expect(await getApprovedHybridCard("sun-pharma", "how-good-is-management")).not.toBeNull();
  });

  it("getApprovedHybridCard with internal key 'sun_pharma' returns null (invalid route)", async () => {
    expect(await getApprovedHybridCard("sun_pharma", "how-good-is-management")).toBeNull();
  });
});

// ── SC7: getLandingCompanies surfaces sun-pharma ─────────────────────────────
describe("SC7 – getLandingCompanies surfaces public slugs", () => {
  it("getLandingCompanies contains an entry with slug 'sun-pharma'", async () => {
    const companies = await getLandingCompanies();
    const sunPharma = companies.find((c) => c.slug === "sun-pharma");
    expect(sunPharma).toBeDefined();
  });

  it("all landing company slugs are URL-safe", async () => {
    const companies = await getLandingCompanies();
    for (const { slug } of companies) {
      expect(slug).toMatch(/^[a-z0-9-]+$/);
    }
  });
});

// ── SC8: getCompanySlugs is consistent with getLandingCompanies ───────────────
describe("SC8 – getCompanySlugs consistency", () => {
  it("getCompanySlugs and getLandingCompanies have the same slug set", async () => {
    const [slugs, companies] = await Promise.all([getCompanySlugs(), getLandingCompanies()]);
    expect([...slugs].sort()).toEqual(companies.map((c) => c.slug).sort());
  });
});

// ── SC9: no company-specific hardcoding in production files ──────────────────
describe("SC9 – no hardcoded company identity conditions in production source", () => {
  it("company-discovery.ts contains no literal equality gates for any company slug", async () => {
    const { readFile } = await import("node:fs/promises");
    const source = await readFile(
      path.resolve("src/lib/ask-intrinsiciq/company-discovery.ts"),
      "utf8",
    );
    for (const slug of ["sun_pharma", "sun-pharma", "ujjivan", "tanla"]) {
      const gates = [...source.matchAll(new RegExp(`=== ?["']${slug}["']`, "g"))];
      expect(gates, `${slug} appears as a literal gate in company-discovery.ts`).toHaveLength(0);
    }
  });

  it("load-company-research-view.ts contains no literal equality gates for any company slug", async () => {
    const { readFile } = await import("node:fs/promises");
    const source = await readFile(
      path.resolve("src/lib/ask-intrinsiciq/load-company-research-view.ts"),
      "utf8",
    );
    for (const slug of ["sun_pharma", "sun-pharma", "ujjivan", "tanla"]) {
      const gates = [...source.matchAll(new RegExp(`=== ?["']${slug}["']`, "g"))];
      expect(gates, `${slug} appears as a literal gate in load-company-research-view.ts`).toHaveLength(0);
    }
  });
});
