import { describe, expect, it } from "vitest";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { tmpdir } from "node:os";
import {
  getCompanyResearchView,
  getLandingCompanies,
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
});
