import { describe, expect, it } from "vitest";
import { evidenceHref, findCitations } from "./cite";

describe("citations are recognised only when they name a year AND a page", () => {
  it.each([
    ["Annual report FY26, p.107", "fy26", 107],
    ["Annual report FY24, p.87 — Risk table", "fy24", 87],
    ["(FY25 annual report p.103)", "fy25", 103],
    ["reported 47% in FY25 (FY25 annual report p.103)", "fy25", 103],
  ])("%s", (text, fy, page) => {
    const [c] = findCitations(text);
    expect([c.fy, c.page]).toEqual([fy, page]);
    expect(text.slice(c.start, c.end)).toMatch(/annual report/i);
  });
  it("never links an ambiguous or incomplete citation", () => {
    for (const t of ["(annual report p.87)", "(p.35)", "Annual report FY26", "Q3 and Q4 FY25 decks p.3", "Capital-allocation ledger, FY23", "p.12 of the report"])
      expect(findCitations(t), t).toEqual([]);
  });
  it("finds several citations in one sentence, in order", () => {
    const t = "June 2024 (FY25 annual report p.10) and June 3, 2025 (FY25 annual report p.35); Annual report FY26, p.136";
    expect(findCitations(t).map((c) => c.page)).toEqual([10, 35, 136]);
  });
  it("builds a page-anchored internal link", () => {
    expect(evidenceHref("sun-pharma", "fy24", 87)).toBe("/evidence/sun-pharma/fy24#page=87");
  });
});
