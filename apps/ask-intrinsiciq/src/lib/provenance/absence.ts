// M63/G5: claim-linked absence provenance for the Story, Panel and Explorer surfaces.
// The ledger is generated outside the app (tools/g5_build_sidecar.py) from the same classifier and evidence resolver that audit the answers, and lives next to the
// company's other records as g5_absence_provenance.json. When it is absent nothing changes: no claim is invented, no state is shown.
import path from "node:path";
import { getRepoRoot } from "@/src/lib/ask-intrinsiciq/paths";
import { readJsonIfExists } from "@/src/lib/prometheus/read-json";
import { COMPANIES } from "@/src/lib/story/companies";

export type AbsenceEntry = {
  claim: string;          // the exact clause as rendered (for a labelled table row: "row label: label text")
  anchor?: string;        // the rendered string that carries the claim, when it is a part of `claim` (a row label, or the text a label such as "Not extracted" qualifies)
  kind?: "absence" | "system_limitation" | "system_coverage";
  topic: string;
  state: "NOT_EXTRACTED" | "NOT_DISCLOSED" | "NOT_APPLICABLE" | null;
  verification: "VERIFIED" | "PENDING_HUMAN_CONFIRMATION" | "UNRESOLVED" | "CONTRADICTED";
  basis: string;
  locator: string;
  evidence_group: string;
  review?: string | null;
  record_statement_ok?: boolean;   // a record-level statement the destination probe confirmed: kept as written
  replacement?: string | null;     // what the investor reads instead when the claim is not verified (built by the same gate that built the ledger)
  supplement?: string | null;      // for a VERIFIED claim: the verified source figure it was checked against, appended once
  sentence?: string;               // the rendered sentence the claim sits in; the replacement takes its place
};

/** Internal verification / pipeline keys (g4_*, g5_*, g41_*) never belong in investor-facing objects. */
export const INTERNAL_KEY = /^g[45]\d*_/;

export async function loadAbsenceLedger(slug: string, opts: { repoRoot?: string } = {}): Promise<AbsenceEntry[]> {
  const company = COMPANIES[slug];
  if (!company) return [];
  const root = opts.repoRoot ?? getRepoRoot();
  const f = await readJsonIfExists<{ entries?: AbsenceEntry[] }>(path.join(root, "companies", company.key, "company_memory", "ask_intrinsiciq", "g5_absence_provenance.json"));
  return f?.entries ?? [];
}

function leaves(v: unknown, out: string[] = []): string[] {
  if (typeof v === "string") out.push(v);
  else if (Array.isArray(v)) v.forEach((x) => leaves(x, out));
  else if (v && typeof v === "object") Object.values(v).forEach((x) => leaves(x, out));
  return out;
}

function mapLeaves<T>(v: T, fn: (s: string) => string): T {
  if (typeof v === "string") return fn(v) as unknown as T;
  if (Array.isArray(v)) return v.map((x) => mapLeaves(x, fn)) as unknown as T;
  if (v && typeof v === "object") return Object.fromEntries(Object.entries(v as object).map(([k, x]) => [k, mapLeaves(x, fn)])) as unknown as T;
  return v;
}

/**
 * The one evidence-safety rule for investor text. An entry that is not VERIFIED, and is not a record statement the destination probe confirmed, never survives as a definitive
 * sentence: the gate's replacement (what is established, what is not, why it matters, what would help) takes its place. Metadata alone is not a gate. Idempotent.
 */
export function enforceEvidenceSafety<T>(surface: T, ledger: AbsenceEntry[]): T {
  const unsafe = ledger.filter((e) => e.replacement && e.verification !== "VERIFIED" && !e.record_statement_ok && (e.sentence || e.claim));
  const verified = ledger.filter((e) => e.verification === "VERIFIED" && e.supplement && !e.anchor);
  if (!unsafe.length && !verified.length) return surface;
  return mapLeaves(surface, (t) => {
    let out = t;
    for (const e of unsafe) {
      const needle = e.sentence && out.includes(e.sentence) ? e.sentence : e.claim;
      if (needle && out.includes(needle) && !out.includes(e.replacement!)) out = out.replace(needle, e.replacement!);
    }
    for (const e of verified) if (out.includes(e.claim) && !out.includes(e.supplement!)) out = out.replace(e.claim, `${e.claim}; ${e.supplement}`);
    return out;
  });
}

/** Enforces the evidence-safety rule on a rendered surface's text and attaches, as a NON-enumerable `g5_absence`, the ledger entries whose claim appears in it (audit access only). */
export function withAbsence<T extends object>(surface: T, ledger: AbsenceEntry[]): T & { g5_absence?: AbsenceEntry[] } {
  if (!ledger.length) return surface;
  const safe = enforceEvidenceSafety(surface, ledger);
  const text = leaves(surface);
  const hit = ledger.filter((e) => text.some((t) => t.includes(e.anchor ?? e.claim)));
  if (!hit.length) return safe;
  const out = { ...safe } as T & { g5_absence?: AbsenceEntry[] };
  Object.defineProperty(out, "g5_absence", { value: hit, enumerable: false });      // audit access only: never enumerated into a customer payload
  return out;
}
