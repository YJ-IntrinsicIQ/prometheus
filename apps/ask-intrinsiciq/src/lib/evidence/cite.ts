// Pure helpers (safe on server and client) for turning a textual citation into a document reference.
// Only citations that name BOTH a fiscal year and a page are recognised ("Annual report FY26, p.107" or
// "FY26 annual report p.107"). "(p.35)" or "annual report p.87" alone is ambiguous and is never linked.
export type Citation = { start: number; end: number; fy: string; page: number };

const PATTERN = /Annual report FY(\d{2})(?:,|\s—|\s–)?\s*p\.\s?(\d{1,4})|FY(\d{2}) annual report,?\s*p\.\s?(\d{1,4})/gi;

export function findCitations(text: string): Citation[] {
  const out: Citation[] = [];
  for (const m of text.matchAll(PATTERN)) {
    const fy = m[1] ?? m[3], page = m[2] ?? m[4];
    out.push({ start: m.index!, end: m.index! + m[0].length, fy: `fy${fy}`, page: Number(page) });
  }
  return out;
}

export const evidenceHref = (companySlug: string, fy: string, page: number) => `/evidence/${companySlug}/${fy}#page=${page}`;
