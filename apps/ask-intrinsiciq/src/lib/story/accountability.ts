// Promise → Action → Outcome chains and the "Words vs Actions" scorecard.
// Presentation only, from the approved commitments register. A promise is never linked to an action or an
// outcome unless a record links them; this module does not create links, so the page says "not established".
import { clean, fyNum } from "./story-adapter";

export type Status = "Delivered" | "Partially delivered" | "Delayed or missed" | "Still in progress" | "Not verified";
export const STATUSES: Status[] = ["Delivered", "Partially delivered", "Delayed or missed", "Still in progress", "Not verified"];

export type Chain = {
  id: string;
  year: string;
  promise: string;
  deadline: string | null;
  status: Status;
  reason: string;
  actionNote: string; // why no action is shown
  evidence: string[];
};

export type Accountability = {
  chains: Chain[];
  total: number;
  counts: Record<Status, number>;
  basis: string;
  notMeasurable: number;
  rules: string[];
};

type Obj = Record<string, unknown>;

/**
 * The deadline a commitment states. The register's canonical classifier stamps `commitment_basis` (text, year, where it came from);
 * only a register written before it falls back to reading the timeframe/statement here.
 */
export function commitmentDeadline(m: Obj, statement = ""): { text: string; year: number | null } | null {
  const basis = m.commitment_basis as { deadline_text?: string | null; deadline_year?: number | null } | undefined;
  if (basis && "deadline_text" in basis) return basis.deadline_text ? { text: basis.deadline_text, year: basis.deadline_year ?? null } : null;
  const f = `${String(m.expected_timeframe ?? "")} ${statement}`;
  const half = /H([12])CY(\d{2})/.exec(f);
  if (half) return { text: `H${half[1]} 20${half[2]}`, year: 2000 + Number(half[2]) };
  const by = /[Bb]y\s+(20\d{2})/.exec(f);
  return by ? { text: `by ${by[1]}`, year: Number(by[1]) } : null;
}

function deadlineOf(m: Obj, statement: string): string | null {
  const d = commitmentDeadline(m, statement);
  return d ? (d.year && !/^h[12]/i.test(d.text) ? `by ${d.year}` : d.text) : null;
}

const statusOf = (raw: unknown): Status => {
  const rs = String(raw ?? "").toLowerCase();
  return /partial/.test(rs) ? "Partially delivered" : /delay|miss/.test(rs) ? "Delayed or missed" : /progress/.test(rs) ? "Still in progress" : /deliver|complete|fulfil/.test(rs) ? "Delivered" : "Not verified";
};

export function buildAccountability(input: { commitments: Obj[]; projects: Obj[] }): Accountability {
  const seen = new Set<string>();
  const chains: Chain[] = [];
  for (const m of input.commitments) {
    if (m.verification_applicability !== "APPLICABLE") continue;
    const id = String(m.id ?? "");
    const fp = String(m.commitment_fingerprint ?? id);
    if (seen.has(fp)) continue; // one entry per distinct commitment
    seen.add(fp);
    const statement = clean(String(m.original_statement ?? "")).replace(/\.$/, "");
    const status = statusOf(m.status);
    const linked = (input.projects.find((p) => ((p.candidate_commitment_links as Obj[] | undefined) ?? []).some((l) => l.commitment_id === id)) ?? null) as Obj | null;
    const ref = ((m.source_references as Obj[] | undefined) ?? [])[0];
    chains.push({
      id: `chain-${chains.length + 1}`,
      year: `FY${fyNum(String(m.announcement_period ?? "")) ?? 0}`,
      promise: statement,
      deadline: deadlineOf(m, statement),
      status,
      reason: status === "Not verified"
        ? "No later evidence in the records confirms or contradicts this commitment. Missing disclosure is not counted as failure."
        : "Status as recorded in the approved commitments register.",
      actionNote: linked
        ? `A project record ("${String(linked.project_name)}") is only a candidate match based on word overlap, so no link is established.`
        : "No execution evidence is linked to this commitment in the records.",
      evidence: ref ? [`Annual report FY${fyNum(String(ref.period))}, p.${ref.page ?? "n/a"}`] : [],
    });
  }
  chains.sort((a, b) => a.year.localeCompare(b.year));
  const counts = Object.fromEntries(STATUSES.map((st) => [st, chains.filter((c) => c.status === st).length])) as Record<Status, number>;
  return {
    chains,
    total: chains.length,
    counts,
    basis: chains.every((c) => c.status === "Not verified")
      ? "The approved commitments register lists each of these as unable to verify."
      : "Statuses as recorded in the approved commitments register.",
    notMeasurable: input.commitments.length - chains.length,
    rules: [
      "Counted: commitments the register marks as verifiable (a specific, checkable target). Duplicates are merged.",
      "Delivered, partially delivered, still in progress, delayed or missed: only as recorded in the register.",
      "Not verified: the records hold no evidence either way. This is missing disclosure, not failure.",
    ],
  };
}
