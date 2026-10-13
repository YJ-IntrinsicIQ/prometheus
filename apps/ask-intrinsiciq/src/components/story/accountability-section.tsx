"use client";

import { useState, type ReactNode } from "react";
import type { Accountability, Chain, Status } from "@/src/lib/story/accountability";
import { STATUSES } from "@/src/lib/story/accountability";
import { Cited } from "./evidence";

const STATUS_STYLE: Record<Status, { dot: string; text: string }> = {
  Delivered: { dot: "bg-accent", text: "text-accent" },
  "Partially delivered": { dot: "bg-gold", text: "text-[#6f5320]" },
  "Delayed or missed": { dot: "bg-[#9a5b4f]", text: "text-[#7a4036]" },
  "Still in progress": { dot: "bg-foreground/40", text: "text-foreground" },
  "Not verified": { dot: "border border-muted bg-transparent", text: "text-muted" },
};

function StatusMark({ status }: { status: Status }) {
  const s = STATUS_STYLE[status];
  return (
    <span className={`inline-flex items-center gap-2 text-[0.82rem] font-medium ${s.text}`}>
      <span aria-hidden className={`h-2.5 w-2.5 rounded-full ${s.dot}`} />
      {status}
    </span>
  );
}

const label = "text-[0.72rem] font-semibold uppercase tracking-[0.12em] text-muted";

function Step({ title, children, empty }: { title: string; children: ReactNode; empty?: boolean }) {
  return (
    <div className={`rounded-[18px] p-4 ${empty ? "border border-dashed border-border" : "bg-surface-strong/60"}`}>
      <p className={label}>{title}</p>
      <div className={`mt-1.5 text-[0.92rem] leading-6 ${empty ? "text-muted" : "text-foreground"}`}>{children}</div>
    </div>
  );
}

const Arrow = () => (
  <span aria-hidden className="flex items-center justify-center text-muted sm:px-1">
    <span className="rotate-90 sm:rotate-0">→</span>
  </span>
);

function ChainCard({ chain }: { chain: Chain }) {
  const [open, setOpen] = useState(false);
  const id = `${chain.id}-evidence`;
  return (
    <li className="rounded-[24px] border border-border bg-surface p-5 shadow-[var(--shadow)]">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-serif text-[1.1rem] text-foreground">
          {chain.year}
          {chain.deadline ? <span className="text-[0.9rem] text-muted"> · due {chain.deadline}</span> : null}
        </span>
        <StatusMark status={chain.status} />
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-[1fr_auto_1fr_auto_1fr]">
        <Step title="Promise">{chain.promise}</Step>
        <Arrow />
        <Step title="Action" empty>Relationship not established. <span className="block text-[0.82rem]">{chain.actionNote}</span></Step>
        <Arrow />
        <Step title="Outcome" empty>Not shown in the records.</Step>
      </div>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((v) => !v)}
        className="mt-3 text-[0.8rem] text-accent"
      >
        {open ? "Hide evidence" : "Show annual-report evidence"}
      </button>
      {open ? (
        <div id={id} className="mt-3 space-y-3 border-t border-border pt-3 text-[0.9rem]">
          <p><span className={label}>Why this status</span><br />{chain.reason}</p>
          <div>
            <p className={label}>Evidence</p>
            <ul className="mt-1 list-disc space-y-1 pl-5">{chain.evidence.map((e) => <li key={e}><Cited text={e} /></li>)}</ul>
          </div>
          <p className="text-[0.78rem] text-muted">
            Counted in the scorecard. Evidence source: approved commitments register. Order in time is not treated as cause and effect.
          </p>
        </div>
      ) : null}
    </li>
  );
}

export function PromiseChains({ data }: { data: Accountability }) {
  return (
    <section id="promise-chains" className="mt-12 scroll-mt-6">
      <h2 className="font-serif text-[1.6rem] text-foreground">Promise → Action → Outcome</h2>
      <p className="mt-1 text-[0.92rem] text-muted">
        Only commitments with a specific, checkable target. Steps are linked only where the records link them; otherwise the page says so.
      </p>
      <ul className="mt-5 space-y-4">{data.chains.map((c) => <ChainCard key={c.id} chain={c} />)}</ul>
    </section>
  );
}

function Column({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <h3 className={label}>{title}</h3>
      <div className="mt-2 space-y-2 text-[0.92rem] leading-6 text-foreground">{children}</div>
    </div>
  );
}

function CountRow({ title, caption, total, counts }: { title: string; caption: string; total: number; counts: Record<Status, number> }) {
  return (
    <div className="border-t border-border pt-4">
      <p className="text-[0.95rem] font-medium text-foreground">{title} <span className="font-normal text-muted">· {total} commitments</span></p>
      <p className="text-[0.82rem] text-muted">{caption}</p>
      <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-5">
        {STATUSES.map((s) => (
          <div key={s}>
            <dd className="font-serif text-[1.9rem] leading-none text-foreground">{counts[s]}</dd>
            <dt className="mt-1"><StatusMark status={s} /></dt>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function Scorecard({ data }: { data: Accountability }) {
  const delivered = data.chains.filter((c) => c.status === "Delivered" || c.status === "Partially delivered");
  const short = data.chains.filter((c) => c.status === "Delayed or missed");
  const unknown = data.chains.filter((c) => c.status === "Not verified" || c.status === "Partially delivered");
  return (
    <section id="words-vs-actions" className="mt-14 scroll-mt-6 rounded-[28px] border border-border bg-surface p-6 sm:p-8">
      <h2 className="font-serif text-[1.7rem] text-foreground">Management: Words vs Actions</h2>
      <p className="mt-2 text-[0.95rem] leading-7 text-muted">
        Of the statements management made in the available reports, <strong className="text-foreground">{data.total}</strong> are marked verifiable in the approved register.
        {" "}{data.notMeasurable} others are intentions or aspirations with no measurable test and are not scored. There is no overall rating: each line below is traceable to a report.
      </p>
      <div className="mt-6">
        <CountRow title="Approved records" caption={data.basis} total={data.total} counts={data.counts} />
      </div>
      <p className="mt-3 text-[0.82rem] text-muted">“Not verified” means the records hold no evidence either way — missing disclosure, not a finding of failure.</p>
      <ol className="mt-4 list-decimal space-y-0.5 pl-5 text-[0.8rem] text-muted">{data.chains.map((c) => <li key={c.id}>{c.promise}</li>)}</ol>
      <div className="mt-8 grid gap-8 sm:grid-cols-3">
        <Column title="Where management delivered">
          {delivered.length ? delivered.map((c) => <p key={c.id}><strong>{c.promise}</strong> — {c.status.toLowerCase()}. {c.reason}</p>) : <p className="text-muted">No commitment is yet evidenced as delivered.</p>}
        </Column>
        <Column title="Where management fell short">
          {short.length ? short.map((c) => <p key={c.id}><strong>{c.promise}</strong> — {c.reason}</p>) : <p className="text-muted">No commitment meets the rule for “delayed or missed”: that needs positive evidence, and none was found.</p>}
        </Column>
        <Column title="What remains unknown">
          {unknown.map((c) => <p key={c.id}><strong>{c.promise}</strong> — {c.status === "Not verified" ? "no outcome is reported in the records." : "the end result and timing are not evidenced."}</p>)}
        </Column>
      </div>
      <details className="mt-8 text-[0.88rem] text-muted">
        <summary className="cursor-pointer text-foreground">How statuses are assigned</summary>
        <ul className="mt-2 list-disc space-y-1 pl-5">{data.rules.map((r) => <li key={r}>{r}</li>)}</ul>
      </details>
    </section>
  );
}
