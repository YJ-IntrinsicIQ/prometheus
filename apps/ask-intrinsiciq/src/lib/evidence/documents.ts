import fs from "node:fs";
import path from "node:path";
import { getRepoRoot } from "@/src/lib/ask-intrinsiciq/paths";
import { COMPANIES } from "@/src/lib/story/companies";

// Filings live at data/Processed/{company}/{fyNN}/annual_report/{company}_{fyNN}.pdf. A link is offered only for a
// file that exists; nothing here builds a URL for a document that cannot be located.
const FY = /^fy\d{2}$/;
const dir = (slug: string) => path.join(getRepoRoot(), "data", "Processed", COMPANIES[slug]?.key ?? "__none__");

export function annualReportPath(slug: string, fy: string): string | null {
  if (!COMPANIES[slug] || !FY.test(fy)) return null;
  const file = path.join(dir(slug), fy, "annual_report", `${COMPANIES[slug].key}_${fy}.pdf`);
  return fs.existsSync(file) ? file : null;
}

/** Fiscal years (e.g. "fy24") for which this company's annual report can be opened. */
export function availableAnnualReports(slug: string): string[] {
  if (!COMPANIES[slug]) return [];
  try {
    return fs.readdirSync(dir(slug)).filter((d) => FY.test(d) && annualReportPath(slug, d)).sort();
  } catch {
    return [];
  }
}
