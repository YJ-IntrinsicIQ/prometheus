"use client";

import type { CommitmentRow, CommitmentStates } from "@/src/lib/story/commitment-evidence";
import { Cited } from "./evidence";

const label = "text-[0.72rem] font-semibold uppercase tracking-[0.12em] text-muted";

// Six things that a single tracker status blurs together, kept apart.
export function CommitmentStatesList({ s, className = "" }: { s: CommitmentStates; className?: string }) {
  const rows: [string, string][] = [
    ["Tracker status", s.tracker],
    ["Evidence of execution", s.execution],
    ["Confirmed delivery", s.delivery],
    ["Target achievement", s.target],
    ["Economic outcome", s.economic],
  ];
  return (
    <dl className={`grid gap-x-6 gap-y-3 sm:grid-cols-2 ${className}`}>
      {rows.map(([k, v]) => (
        <div key={k}>
          <dt className={label}>{k}</dt>
          <dd className="mt-0.5 text-[0.9rem] leading-6 text-foreground">{v}</dd>
        </div>
      ))}
      {s.uncertainty.length ? (
        <div className="sm:col-span-2">
          <dt className={label}>Remaining uncertainty</dt>
          <dd className="mt-0.5 text-[0.9rem] leading-6 text-muted">{s.uncertainty.map((u) => <span key={u} className="block">{u}</span>)}</dd>
        </div>
      ) : null}
    </dl>
  );
}

export function CommitmentCards({ rows }: { rows: CommitmentRow[] }) {
  return (
    <ul className="space-y-4">
      {rows.map((r) => (
        <li key={`${r.period}-${r.promise}`} className="rounded-[24px] border border-border bg-surface p-5 shadow-[var(--shadow)]">
          <p className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="font-serif text-[1.1rem] text-foreground">{r.period}{r.timeframe ? <span className="text-[0.9rem] text-muted"> · {r.timeframe}</span> : null}</span>
            <span className="text-[0.75rem] text-muted">{r.hard ? "Specific target and deadline" : "No deadline — not scored"}</span>
          </p>
          <p className="mt-2 text-[1rem] leading-6 text-foreground">{r.promise}</p>
          <CommitmentStatesList s={r.states} className="mt-4" />
          {r.evidence.length ? (
            <p className="mt-4 text-[0.82rem] text-muted"><span className={label}>Sources </span>{r.evidence.map((e, i) => <span key={e}>{i ? " · " : ""}<Cited text={e} /></span>)}</p>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

export function CommitmentsSection({ rows }: { rows: CommitmentRow[] }) {
  return (
    <section id="commitments" className="mt-12 scroll-mt-6">
      <h2 className="font-serif text-[1.6rem] text-foreground">Commitments: tracker versus evidence</h2>
      <p className="mt-1 text-[0.92rem] text-muted">
        The commitment tracker and the annual reports can disagree: a tracker status of “unable to verify” means the tracker has not been updated, not that nothing happened.
        Each commitment below keeps the tracker status, the evidence of execution, confirmed delivery, target achievement and economic outcome apart.
      </p>
      <div className="mt-5"><CommitmentCards rows={rows} /></div>
    </section>
  );
}
