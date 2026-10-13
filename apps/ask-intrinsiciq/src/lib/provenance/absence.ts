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
};

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

/** Adds `g5_absence` to a rendered surface: the ledger entries whose claim text appears in it. Nothing else in the surface changes. */
export function withAbsence<T extends object>(surface: T, ledger: AbsenceEntry[]): T & { g5_absence?: AbsenceEntry[] } {
  if (!ledger.length) return surface;
  const text = leaves(surface);
  const hit = ledger.filter((e) => text.some((t) => t.includes(e.anchor ?? e.claim)));
  return hit.length ? { ...surface, g5_absence: hit } : surface;
}
