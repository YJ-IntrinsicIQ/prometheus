// Small text helpers shared by the Story builders.
const ID_PATTERN = /\b(?:MC|CL|PJ|CAO|CHK|MP|CM|RG)-\d{2,}(?:-[A-Za-z_]+)?\b:?\s*/g;

export function clean(text: string): string {
  return text
    .replace(ID_PATTERN, "")
    .replace(/\bH([12])CY(\d{2})\b/g, "H$1 20$2")
    .replace(/\bUNABLE_TO_VERIFY\b/g, "unable to verify")
    .replace(/\(\s*,\s*/g, "(")
    .replace(/\s{2,}/g, " ")
    .replace(/^[\s:;,]+/, "")
    .trim();
}

export const fyNum = (p?: string) => {
  const m = /fy\s?(\d{2})/i.exec(p ?? "");
  return m ? Number(m[1]) : null;
};
export const fyLabel = (p?: string) => (fyNum(p) === null ? "n/a" : `FY${fyNum(p)}`);

export const firstSentence = (t: string, max = 170) => {
  const s = clean(t).split(/(?<=[.;])\s/)[0].replace(/[\s;:,]+$/, "");
  return s.length <= max ? s : `${s.slice(0, max - 1).replace(/\s+\S*$/, "")}…`;
};

export const cr = (n: number) => `₹${Math.round(n).toLocaleString("en-IN")} cr`;
export const sentenceCase = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);
