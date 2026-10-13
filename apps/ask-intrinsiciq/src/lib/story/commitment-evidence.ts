import { findCitations } from "@/src/lib/evidence/cite";
import { clean, sentenceCase } from "./text";

// Commitment evidence, read from the company's APPROVED answers to "What has management promised?" and "What did
// management actually deliver?". It keeps six things apart that a single tracker status blurs together: the tracker's
// status, evidence of execution, confirmed delivery, target achievement, economic outcome, and what is still uncertain.
// Nothing is inferred: every cell is a stored phrase or a plain comparison of stored figures.
type Obj = Record<string, unknown>;

export type CommitmentStates = { tracker: string; execution: string; delivery: string; target: string; economic: string; uncertainty: string[] };
export type CommitmentRow = {
  period: string; // "FY24"
  promise: string;
  timeframe: string;
  hard: boolean; // specific target and deadline (the register's canonical classification wins when it carries one)
  hasEvidence: boolean; // later reports state progress or a filing for it
  deliveryClass: "reached" | "partly" | "in_progress" | "unknown";
  observed: { fy: number; value: number; calculated: boolean }[];
  target: number | null;
  states: CommitmentStates;
  evidence: string[]; // citations such as "Annual report FY25, p.103"
};

const tokens = (s: string) => new Set((s.toLowerCase().replace(/™/g, "").match(/[a-z]{5,}/g) ?? []));
const overlaps = (a: string, b: string) => { const t = tokens(b); return [...tokens(a)].some((x) => t.has(x)); };
const strings = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);
const normalize = (fy: string, page: number | string) => `Annual report FY${fy.replace(/\D/g, "")}, p.${page}`;

function citationsOf(segment: string): string[] {
  const out = findCitations(segment).map((c) => normalize(c.fy, c.page));
  // "24.69% in FY25 (p.103)": the year is named by the figure, not the bracket
  for (const m of segment.matchAll(/in FY(\d{2})\s*\((?:annual report )?p\.(\d{1,4})\)/g)) out.push(normalize(m[1], m[2]));
  return [...new Set(out)];
}

/**
 * A row read from approved-answer text is "hard" only if the register's canonical classification (stamped by the one classifier,
 * matched by commitment identity) agrees. A register written before the classifier carries no flag, so the row stays as parsed.
 * The identity is used for the lookup only; it is never shipped in the row.
 */
function canonicalHard(register: Obj[], commitmentId: string): boolean {
  const m = register.find((x) => String(x.id) === commitmentId);
  return typeof m?.hard_commitment === "boolean" ? m.hard_commitment : true;
}

export function parseCommitmentEvidence(promises: Obj | null, delivery: Obj | null, register: Obj[] = []): CommitmentRow[] {
  if (!promises) return [];
  const facts = strings(promises.deterministic_precision_facts);
  const hard = facts.map((s) => /^Hard commitment (\d+) — (MC-\d+) \((FY\d+)\): (.+)$/.exec(s)).filter((m): m is RegExpExecArray => !!m);
  if (!hard.length) return [];

  // The evidence line "Hard commitments: (1) …; (2) …; (3) …" holds the sources for each one.
  const line = strings(promises.what_evidence_shows).find((l) => l.startsWith("Hard commitments:")) ?? "";
  const parts = line.split(/\((\d)\)\s/);
  const segment = new Map<number, string>();
  for (let i = 1; i < parts.length; i += 2) segment.set(Number(parts[i]), (parts[i + 1] ?? "").replace(/;\s*$/, "").trim());

  const dFacts = (Array.isArray(delivery?.deterministic_precision_facts) ? (delivery!.deterministic_precision_facts as unknown[]) : []).filter((x): x is Obj => !!x && typeof x === "object");
  const classes: [RegExp, CommitmentRow["deliveryClass"], string][] = [
    [/^Target level reported reached/, "reached", "Target level reported reached"],
    [/^Partly evidenced/, "partly", "Partly evidenced: filing confirmed; deadline and approval not established"],
    [/^In progress/, "in_progress", "In progress; deadline not yet reached"],
  ];
  const economic = dFacts.find((f) => /^Economic outcomes confirmed/.test(String(f.metric)));
  const economicText = economic && String(economic.value) === "0" ? "None confirmed in the records" : "Not established in the records";
  const unproven = String(delivery?.what_is_not_yet_proven ?? promises.what_is_not_yet_proven ?? "").split(/(?<=\.)\s+(?=[A-Z])/);

  const rows: CommitmentRow[] = hard.map((m) => {
    const n = Number(m[1]);
    const bits = m[4].split("; ");
    const promise = clean(bits[0]);
    const get = (key: string) => bits.find((b) => b.startsWith(`${key}=`))?.slice(key.length + 1);
    const timeframe = ((t) => (/not stated|unspecified|n\/a|^none$/i.test(t) ? "" : t))(clean(get("timeframe") ?? ""));
    const progress = get("reported progress") ?? "";
    const extras = bits.slice(1).filter((b) => !/^(timeframe|reported progress|register status)=/.test(b)).map((b) => clean(b).replace(/\bfy(\d{2})\b/gi, "FY$1"));
    const observed = [...progress.matchAll(/(\d+(?:\.\d+)?)%\s*(calculated\s*)?\(FY(\d{2})\)/g)].map((o) => ({ fy: Number(o[3]), value: Number(o[1]), calculated: !!o[2] }));
    const target = /(\d+(?:\.\d+)?)%/.exec(promise) ? Number(/(\d+(?:\.\d+)?)%/.exec(promise)![1]) : null;
    const cls = classes.map(([re, c, label]) => ({ c, label, hit: dFacts.find((f) => re.test(String(f.metric)) && overlaps(promise, String(f.period))) })).find((x) => x.hit);
    const last = observed[observed.length - 1];
    const reached = target !== null ? observed.find((o) => o.value >= target) : undefined;
    const notDue = extras.some((e) => /not yet reached/i.test(e)) || cls?.c === "in_progress";
    const execution = observed.length
      ? `Reported ${observed.map((o) => `${o.value}%${o.calculated ? " (calculated)" : ""} in FY${o.fy}`).join(", ")}`
      : extras.find((e) => /filing confirmed|reported as filed/i.test(e)) ? sentenceCase(extras.find((e) => /filing confirmed|reported as filed/i.test(e))!) : "No execution evidence in the records";
    return {
      period: m[3],
      promise,
      timeframe,
      hard: canonicalHard(register, m[2]),
      hasEvidence: observed.length > 0 || extras.some((e) => /filing confirmed|reported as filed/i.test(e)),
      deliveryClass: cls?.c ?? "unknown",
      observed,
      target,
      states: {
        tracker: sentenceCase((get("register status") ?? "unknown").toLowerCase()),
        execution,
        delivery: cls?.label ?? "Not established in the records",
        target: reached
          ? `Reached: ${reached.value}% in FY${reached.fy}${reached.calculated ? " (calculated from disclosed quantities)" : ""} against ${target}% ${timeframe}`.trim()
          : target !== null && last
            ? `Not yet reached: ${last.value}% in FY${last.fy} against ${target}% ${timeframe}${notDue ? " — deadline not yet reached" : ""}`.trim()
            : "Not established: " + (extras.filter((e) => /deadline|approval/i.test(e)).join("; ") || "no measurable target level"),
        economic: economicText,
        uncertainty: unproven.filter((s) => overlaps(promise, s)).map(clean).slice(0, 2),
      },
      evidence: citationsOf(segment.get(n) ?? ""),
    };
  });

  // Register-verifiable commitments with no deadline: shown, never scored.
  const other = facts.find((s) => s.startsWith("Other register-verifiable commitments without a deadline:")) ?? "";
  for (const o of other.matchAll(/MC-\d+ \((FY\d+)\) ([^;]+?)(?=;|$)/g))
    rows.push({
      period: o[1], promise: clean(o[2]), timeframe: "no deadline stated", hard: false, hasEvidence: false, deliveryClass: "unknown", observed: [], target: null,
      states: { tracker: "Unable to verify", execution: "No later evidence in the records", delivery: "Not established in the records", target: "No measurable target or deadline", economic: economicText, uncertainty: [] },
      evidence: [],
    });
  return rows;
}

/** The register's own citation for a commitment: the page where management made the statement. */
export function registerSourceOf(commitments: Obj[]) {
  const words = (t: string) => new Set(t.toLowerCase().replace(/™/g, "").match(/[a-z]{5,}/g) ?? []);
  return (r: CommitmentRow): string | null => {
    const want = words(r.promise);
    const m = commitments.find((c) => `FY${/\d+/.exec(String(c.announcement_period))?.[0]}` === r.period && [...words(String(c.original_statement ?? ""))].some((t) => want.has(t)));
    const ref = ((m?.source_references as Obj[] | undefined) ?? [])[0];
    return ref?.page ? `Annual report ${r.period}, p.${ref.page}` : null;
  };
}
