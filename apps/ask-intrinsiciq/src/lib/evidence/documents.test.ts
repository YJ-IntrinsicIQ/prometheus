import fs from "node:fs";
import { describe, expect, it } from "vitest";
import { GET } from "@/app/evidence/[companySlug]/[fiscalYear]/route";
import { annualReportPath, availableAnnualReports } from "./documents";
import { COMPANIES } from "@/src/lib/story/companies";

const call = (slug: string, fy: string, range?: string) =>
  GET(new Request(`http://x/evidence/${slug}/${fy}`, { headers: range ? { range } : {} }), { params: Promise.resolve({ companySlug: slug, fiscalYear: fy }) });
const hasData = annualReportPath("sun-pharma", "fy24") !== null; // the filings are local data, not part of the repository

describe("annual-report documents", () => {
  it("offers only files that exist, for supported companies", () => {
    for (const slug of Object.keys(COMPANIES)) for (const fy of availableAnnualReports(slug)) expect(fs.existsSync(annualReportPath(slug, fy)!), `${slug}/${fy}`).toBe(true);
    expect(annualReportPath("acme", "fy24")).toBeNull();
    expect(annualReportPath("tanla", "fy24")).toBeNull(); // no Tanla FY24 filing exists: no link is produced
  });
  it("rejects anything that is not a plain company slug and fiscal year", async () => {
    for (const [slug, fy] of [["sun-pharma", "../../etc/passwd"], ["sun-pharma", "fy24.pdf"], ["../companies", "fy24"], ["acme", "fy24"], ["sun-pharma", "fy99"]])
      expect((await call(slug, fy)).status, `${slug}/${fy}`).toBe(404);
  });
  it.skipIf(!hasData)("serves the PDF inline, and byte ranges so a viewer can jump to a page", async () => {
    const full = await call("sun-pharma", "fy24");
    expect(full.status).toBe(200);
    expect(full.headers.get("content-type")).toBe("application/pdf");
    expect(full.headers.get("content-disposition")).toMatch(/^inline/);
    await full.body?.cancel();
    const part = await call("sun-pharma", "fy24", "bytes=0-4");
    expect(part.status).toBe(206);
    expect(new TextDecoder().decode(await part.arrayBuffer())).toBe("%PDF-");
    expect((await call("sun-pharma", "fy24", "bytes=999999999999-")).status).toBe(416);
  });
});
