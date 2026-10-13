"use client";

import { useState, type ReactNode } from "react";
import type { Block, Body, QuestionView } from "@/src/lib/story/question-view";
import { PromiseChains } from "./accountability-section";
import { ConnectionCard } from "./connections-section";
import { DiscoveriesSection, Visual } from "./discoveries-section";
import Link from "next/link";
import type { CatalogQuestion } from "@/src/lib/catalog/catalog";
import { SPECIALISTS } from "@/src/lib/panel/specialists";
import { CockpitShell, Unavailable } from "./cockpit-shell";
import { CommitmentCards } from "./commitment-section";
import { Cited } from "./evidence";
import { highlight } from "./story-view";

const label = "text-[0.72rem] font-semibold uppercase tracking-[0.12em] text-muted";
const STATE_TONE: Record<string, string> = {
  worsening: "bg-[#9a5b4f]", recurring: "bg-gold", improving: "bg-accent", mitigation: "bg-accent/70", new: "bg-foreground/60", "not reconfirmed": "bg-muted/50",
};

function Spans({ body }: { body: Extract<Body, { kind: "spans" }> }) {
  const [all, setAll] = useState(false);
  const [openRow, setOpenRow] = useState<string | null>(null);
  const [a, b] = body.axis, n = b - a + 1;
  const rows = all ? body.rows : body.rows.slice(0, 8);
  return (
    <div className="mt-3">
      <div className="grid grid-cols-[minmax(110px,1.3fr)_3fr] gap-x-3 text-[0.72rem] text-muted sm:grid-cols-[minmax(160px,1.1fr)_3fr]">
        <span>Fiscal year</span>
        <div className="grid" style={{ gridTemplateColumns: `repeat(${n}, 1fr)` }}>
          {Array.from({ length: n }, (_, i) => <span key={i} className="text-center">{String(a + i).slice(2)}</span>)}
        </div>
      </div>
      <ul className="mt-1 space-y-1.5">
        {rows.map((r) => {
          const tone = Object.entries(STATE_TONE).find(([k]) => r.state.startsWith(k))?.[1] ?? "bg-foreground/40";
          return (
            <li key={r.label} className="grid grid-cols-[minmax(110px,1.3fr)_3fr] items-center gap-x-3 text-[0.82rem] sm:grid-cols-[minmax(160px,1.1fr)_3fr]">
              <span className="text-foreground">
                {r.full !== r.label ? (
                  <button type="button" title={r.full} aria-expanded={openRow === r.label} onClick={() => setOpenRow(openRow === r.label ? null : r.label)} className="text-left underline decoration-dotted underline-offset-4">
                    {openRow === r.label ? r.full : r.label}
                  </button>
                ) : r.label}
                <span className="block text-[0.72rem] text-muted">{r.state}</span>
              </span>
              <div className="relative grid h-3 rounded-full bg-surface-strong" style={{ gridTemplateColumns: `repeat(${n}, 1fr)` }} role="img" aria-label={`${r.label}: ${r.note}, ${r.state}`}>
                <span className={`rounded-full ${tone}`} style={{ gridColumn: `${Math.max(1, r.from - a + 1)} / ${Math.min(n, r.to - a + 1) + 1}` }} />
              </div>
            </li>
          );
        })}
      </ul>
      {body.rows.length > 8 ? (
        <button type="button" onClick={() => setAll((v) => !v)} className="mt-3 text-[0.82rem] text-accent">{all ? "Show fewer risks" : `Show all ${body.rows.length} risks`}</button>
      ) : null}
    </div>
  );
}

function BlockBody({ body }: { body: Body }): ReactNode {
  switch (body.kind) {
    case "visual": return <Visual v={body.visual} />;
    case "commitments": return <div className="mt-4"><CommitmentCards rows={body.rows} /></div>;
    case "spans": return <Spans body={body} />;
    case "connections": return <ul className="mt-4 space-y-5">{body.items.map((c) => <ConnectionCard key={c.id} c={c} />)}</ul>;
    case "consistency":
      return (
        <ul className="mt-3 grid gap-3 sm:grid-cols-2">
          {body.items.map((i) => (
            <li key={i.label} className="rounded-[18px] border border-border bg-surface-strong/50 p-4">
              <p className="font-serif text-[1.02rem] text-foreground">{i.label}</p>
              <p className="mt-0.5 text-[0.78rem] font-semibold uppercase tracking-wide text-accent">{i.status}</p>
              <p className="mt-1 text-[0.88rem] leading-6 text-muted">{i.text}</p>
            </li>
          ))}
        </ul>
      );
    default: return null;
  }
}

function BlockView({ b }: { b: Block }) {
  if (b.body.kind === "chains") return <div><p className="text-[0.82rem] text-muted">{b.caption}</p><PromiseChains data={b.body.data} /></div>;
  return (
    <section className="rounded-[24px] border border-border bg-surface p-5 shadow-[var(--shadow)] sm:p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-serif text-[1.25rem] text-foreground">{b.title}</h3>
        <span className="rounded-full bg-accent-soft px-2.5 py-0.5 text-[0.7rem] font-medium text-accent">Approved records</span>
      </div>
      <p className="mt-1 text-[0.88rem] text-muted">{b.caption}</p>
      <BlockBody body={b.body} />
    </section>
  );
}

function Drill({ title, children, open }: { title: string; children: ReactNode; open?: boolean }) {
  return (
    <details open={open} className="rounded-[18px] border border-border bg-surface px-4 py-3">
      <summary className="cursor-pointer text-[0.95rem] font-medium text-foreground">{title}</summary>
      <div className="mt-3 text-[0.9rem] leading-6 text-foreground">{children}</div>
    </details>
  );
}
const List = ({ items }: { items: string[] }) => (items.length ? <ul className="list-disc space-y-1.5 pl-5">{items.map((i) => <li key={i}><Cited text={i} /></li>)}</ul> : <p className="text-muted">Nothing recorded.</p>);

function Original({ v }: { v: unknown }): ReactNode {
  if (v == null || v === "") return <span className="text-muted">(empty)</span>;
  if (typeof v === "string") return <span><Cited text={v} /></span>;
  if (typeof v === "number" || typeof v === "boolean") return <span>{String(v)}</span>;
  if (Array.isArray(v)) return v.length ? <ul className="list-disc space-y-1 pl-5">{v.map((x, i) => <li key={i}><Original v={x} /></li>)}</ul> : <span className="text-muted">(none)</span>;
  return <ul className="list-disc space-y-1 pl-5">{Object.entries(v as Record<string, unknown>).map(([k, x]) => <li key={k}><strong>{k.replace(/_/g, " ")}: </strong><Original v={x} /></li>)}</ul>;
}

/** Where the investor is: company → research area → this question, with a way back. */
function ReadingContext({ view }: { view: QuestionView }) {
  const c = view.context;
  return (
    <nav aria-label="You are here" className="mt-6 text-[0.82rem] text-muted">
      <Link href={`/company/${view.slug}`} className="text-accent hover:underline">{view.company}</Link>
      <span aria-hidden> › </span>
      {c ? <Link href={`/company/${view.slug}/questions#${c.familyId}`} className="text-accent hover:underline">{c.stage === c.familyTitle ? c.familyTitle : `${c.stage} · ${c.familyTitle}`}</Link> : <span>{view.question.family}</span>}
      <span aria-hidden> › </span>
      <span aria-current="page" className="text-foreground">{view.question.title}</span>
    </nav>
  );
}

const SECTIONS: [string, string][] = [["answer", "The answer"], ["why", "Why it matters"], ["evidence", "Supporting evidence"], ["unknown", "What remains unknown"], ["next", "What to investigate next"]];

export function QuestionExperience({ view }: { view: QuestionView }) {
  const d = view.drilldown;
  const sections = SECTIONS.filter(([id]) => id !== "why" || view.takeaway);
  return (
    <CockpitShell slug={view.slug} company={view.company} available={view.available} docs={view.docs} titles={view.titles} activeQuestion={view.question.id}>
      <ReadingContext view={view} />
      <h1 className="mt-3 font-serif text-[2rem] leading-tight text-foreground sm:text-[2.4rem]">{view.question.title}</h1>
      <p className="mt-2 text-[0.88rem] text-muted">
        {view.question.family} · Evidence period {view.period} · <span className="text-accent">Approved answer</span>
      </p>
      {view.periodNote ? <p className="mt-1 text-[0.8rem] leading-5 text-muted">{view.periodNote}</p> : null}
      <nav aria-label="On this page" className="mt-4 flex flex-wrap gap-x-4 gap-y-1 border-y border-border py-2 text-[0.8rem]">
        {sections.map(([id, t]) => <a key={id} href={`#${id}`} className="text-accent hover:underline">{t}</a>)}
      </nav>

      {/* 1. The answer: what does the evidence establish? */}
      <section id="answer" className="mt-6 scroll-mt-6" aria-label="The answer">
        <h2 className="sr-only">The answer</h2>
        <p className="rounded-[20px] bg-gold-soft/70 p-5 font-serif text-[1.2rem] leading-snug text-foreground">{highlight(view.conclusion)}</p>
        {view.facts.length ? (
          <dl className="mt-4 grid grid-cols-[repeat(auto-fit,minmax(120px,1fr))] gap-3">
            {view.facts.map((f) => (
              <div key={f.label} className="rounded-[18px] border border-border bg-surface p-4">
                <dd className={`font-serif leading-tight text-accent ${f.value.length > 24 ? "text-[1.02rem]" : f.value.length > 7 ? `${/^[₹\d.,]+( Cr| of \d+|%)?$|^[^ ]+$/.test(f.value) ? "whitespace-nowrap " : ""}text-[1.2rem]` : "text-[1.5rem]"}`}>{f.value.includes("→") ? f.value.split(/\s*→\s*/).map((p, i) => <span key={i} className="block">{i ? "→ " : ""}{p}</span>) : f.value}</dd>
                <dt className="mt-1 text-[0.8rem] leading-5 text-muted">{f.label}{f.period ? ` · ${f.period}` : ""}</dt>
                {f.note ? <dd className="mt-0.5 text-[0.75rem] leading-4 text-muted">{f.note}</dd> : null}
              </div>
            ))}
          </dl>
        ) : null}
        {view.notices.map((n) => (
          <aside key={n.id} role="note" className="mt-4 rounded-[18px] border border-dashed border-gold bg-surface p-4 text-[0.88rem] leading-6">
            <p className="font-medium text-[#6f5320]">{n.title}</p>
            <p className="mt-1 text-foreground">{n.text}</p>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-muted">{n.items.map((i) => <li key={i}>{i}</li>)}</ul>
          </aside>
        ))}
      </section>

      {/* 2. Why it matters: the investment significance, from the approved answer's own economic reading */}
      {view.takeaway ? (
        <section id="why" className="mt-8 scroll-mt-6" aria-label="Why it matters">
          <h2 className="font-serif text-[1.4rem] text-foreground">Why it matters</h2>
          <p className="mt-2 text-[0.98rem] leading-7 text-foreground">{view.takeaway}</p>
        </section>
      ) : null}

      {/* 3. Supporting evidence: where the conclusion comes from */}
      <section id="evidence" className="mt-10 scroll-mt-6" aria-label="Supporting evidence">
        <h2 className="font-serif text-[1.6rem] text-foreground">Supporting evidence</h2>
        {view.blocks.length ? <div className="mt-4 space-y-5">{view.blocks.map((b) => <BlockView key={b.id} b={b} />)}</div> : null}
        {view.discoveries.length ? <DiscoveriesSection discoveries={view.discoveries} title="Related discoveries" intro="Findings from the Discoveries view that bear on this question." className="mt-8" /> : null}
        <div className="mt-4 space-y-3">
          <Drill title="Supporting facts"><List items={d.facts} /></Drill>
          <Drill title="Historical observations"><List items={d.observations} /></Drill>
          <Drill title="Source references"><List items={d.sources} /></Drill>
          <Drill title="Complete original analysis">
            <p className="mb-3 text-[0.8rem] text-muted">The stored answer, every field. Only internal codes and identifiers are reworded for readability; the content is unchanged.</p>
            <div className="space-y-4">{d.original.map((o) => <div key={o.label}><p className={label}>{o.label}</p><div className="mt-1"><Original v={o.value} /></div></div>)}</div>
          </Drill>
        </div>
      </section>

      {/* 4. What remains unknown: what not to assume */}
      <section id="unknown" className="mt-10 scroll-mt-6 rounded-[24px] border border-dashed border-gold bg-surface p-5" aria-label="What remains unknown">
        <h2 className="font-serif text-[1.4rem] text-foreground">What remains unknown</h2>
        <p className="mt-1 text-[0.85rem] text-muted">Avoid assuming more than the evidence above establishes.</p>
        <div className="mt-3 text-[0.92rem] leading-6 text-foreground"><List items={d.limitations} /></div>
      </section>

      {/* 5. What to investigate next */}
      <section id="next" className="mt-10 scroll-mt-6" aria-label="What to investigate next">
        <h2 className="font-serif text-[1.6rem] text-foreground">What to investigate next</h2>
        {view.related?.length ? (
          <ul className="mt-3 space-y-2">
            {view.related.map((r) => (
              <li key={r.id} className="rounded-[16px] border border-border bg-surface px-4 py-3">
                <Link href={r.href} className="font-medium text-accent underline-offset-4 hover:underline">{r.title}</Link>
                <span className="mt-0.5 block text-[0.84rem] text-muted">{r.why}</span>
              </li>
            ))}
          </ul>
        ) : null}
        {d.monitor.length ? (
          <div className="mt-5">
            <p className={label}>Watch for</p>
            <div className="mt-1 text-[0.92rem] leading-6 text-foreground"><List items={d.monitor} /></div>
          </div>
        ) : null}
        {view.panels?.length ? (
          <p className="mt-5 text-[0.88rem] text-muted"><span className={label}>Investment Panel </span>{view.panels.map((p, i) => <span key={p.id}>{i ? " · " : ""}<Link href={p.href} className="text-accent hover:underline">{p.name}</Link></span>)} use this answer.</p>
        ) : null}
        <p className="mt-5 flex flex-wrap gap-x-5 gap-y-1 text-[0.9rem]">
          {view.next ? <Link href={view.next.href} className="text-accent underline-offset-4 hover:underline">Continue: {view.next.label} →</Link> : null}
          <Link href={`/company/${view.slug}/questions${view.context ? `#${view.context.familyId}` : ""}`} className="text-accent underline-offset-4 hover:underline">← All {view.context?.familyTitle ?? view.question.family} questions</Link>
          <Link href={`/company/${view.slug}`} className="text-accent underline-offset-4 hover:underline">← {view.company}: The Story</Link>
        </p>
      </section>
    </CockpitShell>
  );
}

/** A valid catalog question whose answer is not (yet) certified for this company. Nothing is shown in place of an answer. */
export function QuestionPending({ slug, company, available, docs, titles, question, familyTitle, familyId, entry, related }: {
  slug: string; company: string; available: string[]; docs: string[]; titles?: Record<string, string>; familyId?: string;
  question: { id: string; title: string };
  familyTitle: string;
  entry: CatalogQuestion | null;
  related: { id: string; title: string; href: string; why?: string }[];
}) {
  return (
    <CockpitShell slug={slug} company={company} available={available} docs={docs} titles={titles} activeQuestion={question.id}>
      <nav aria-label="You are here" className="mt-6 text-[0.82rem] text-muted">
        <Link href={`/company/${slug}`} className="text-accent hover:underline">{company}</Link><span aria-hidden> › </span>
        <Link href={`/company/${slug}/questions${familyId ? `#${familyId}` : ""}`} className="text-accent hover:underline">{familyTitle}</Link><span aria-hidden> › </span>
        <span aria-current="page" className="text-foreground">{question.title}</span>
      </nav>
      <h1 className="mt-1 font-serif text-[2rem] leading-tight text-foreground sm:text-[2.4rem]">{question.title}</h1>
      <Unavailable title="Answer not yet available">
        Prometheus supports this question, but its answer for {company} is awaiting evidence validation and certification. Nothing is shown in its place: no draft, generated or borrowed answer, and nothing from another company.
        {entry ? <span className="mt-3 block text-[0.88rem]">{entry.drawsOn.length ? `What it investigates draws on ${entry.drawsOn.join(", ")}. ` : ""}{entry.basis}.</span> : null}
      </Unavailable>
      {related.length ? (
        <section className="mt-8" aria-label="Related certified answers">
          <h2 className="font-serif text-[1.3rem] text-foreground">Related questions with a certified answer</h2>
          <ul className="mt-3 space-y-1.5 text-[0.92rem]">{related.map((r) => <li key={r.id}><Link href={r.href} className="text-accent underline-offset-4 hover:underline">{r.title}</Link>{r.why ? <span className="block text-[0.82rem] text-muted">{r.why}</span> : null}</li>)}</ul>
        </section>
      ) : null}
      {entry?.specialists.length ? (
        <p className="mt-6 text-[0.88rem] text-muted">Used by the Investment Panel: {entry.specialists.map((id, i) => <span key={id}>{i ? " · " : ""}<Link href={`/company/${slug}/panel/${id}`} className="text-accent hover:underline">{SPECIALISTS.find((x) => x.id === id)!.name}</Link></span>)}</p>
      ) : null}
      <p className="mt-6 text-[0.88rem]"><Link href={`/company/${slug}/questions`} className="text-accent hover:underline">← All {company} questions</Link></p>
    </CockpitShell>
  );
}
