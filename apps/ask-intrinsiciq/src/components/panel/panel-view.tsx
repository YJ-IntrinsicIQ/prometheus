"use client";

import Link from "next/link";
import type { Obs, Panel, SpecialistView } from "@/src/lib/panel/build-panel";
import { CockpitShell } from "@/src/components/story/cockpit-shell";
import { Cited } from "@/src/components/story/evidence";
import { PanelNav, panelRoute } from "./panel-nav";

const label = "text-[0.72rem] font-semibold uppercase tracking-[0.12em] text-muted";
const BASIS: Record<Obs["basis"], string> = {
  Reported: "bg-surface-strong text-foreground",
  Calculated: "bg-accent-soft text-accent",
  "Approved answer": "bg-gold-soft text-[#6f5320]",
  Interpretation: "border border-dashed border-border text-muted",
};
const PROVENANCE = "Built only from approved answers and canonical records. Reported = a stored figure; Calculated = arithmetic on stored figures; Approved answer = from an answer that passed approval; Interpretation = a fixed, hedged reading under the framework. No ratings, valuations or recommendations are produced; earlier model-written panel analyses in company memory are not approved and are not used.";

function Basis({ b }: { b: Obs["basis"] }) {
  return <span className={`rounded-full px-2.5 py-0.5 text-[0.7rem] font-medium ${BASIS[b]}`}>{b}</span>;
}

function LensChips({ s }: { s: SpecialistView }) {
  return (
    <ul className="flex flex-wrap gap-1.5 text-[0.75rem]" aria-label="Evidence lenses">
      {s.lenses.map((l) => (
        <li key={l.name} className={`rounded-full border px-2.5 py-1 ${l.available ? "border-accent/40 bg-accent-soft/60 text-foreground" : "border-dashed border-border text-muted"}`} title={l.available ? "Some evidence in the records" : "No evidence in the records"}>
          <span aria-hidden>{l.available ? "● " : "○ "}</span>{l.name}<span className="sr-only">{l.available ? " (evidence available)" : " (no evidence)"}</span>
        </li>
      ))}
    </ul>
  );
}

function ObsCard({ o }: { o: Obs }) {
  return (
    <li className="rounded-[20px] border border-border bg-surface p-4">
      <div className="flex flex-wrap items-center gap-2"><Basis b={o.basis} /></div>
      <p className="mt-2 text-[0.95rem] leading-7 text-foreground"><Cited text={o.text} /></p>
      <p className="mt-2 text-[0.78rem] text-muted"><span className={label}>Sources </span>{o.sources.map((src, i) => <span key={src}>{i ? " · " : ""}<Cited text={src} /></span>)}{o.link ? <> · <Link href={o.link.href} className="text-accent hover:underline">{o.link.label} →</Link></> : null}</p>
    </li>
  );
}

export function PanelOverview({ panel }: { panel: Panel }) {
  return (
    <CockpitShell slug={panel.slug} company={panel.company} available={panel.available} docs={panel.docs} titles={panel.titles} panel>
      <h1 className="mt-6 font-serif text-[2.1rem] leading-tight text-foreground sm:text-[2.6rem]">{panel.company}: Investment Panel</h1>
      <p className="mt-2 max-w-2xl text-[0.95rem] leading-7 text-muted">Five investing frameworks, one evidence base. Each perspective reads the same approved answers and canonical records through a different question — and says plainly where the records fall short.</p>
      <PanelNav slug={panel.slug} />
      <ul className="mt-6 grid gap-4 md:grid-cols-2">
        {panel.specialists.map((s) => {
          const shown = s.observations.slice(0, 3);
          const have = s.lenses.filter((l) => l.available).length;
          return (
            <li key={s.id} className="flex flex-col rounded-[24px] border border-border bg-surface p-5 shadow-[var(--shadow)]">
              <p className={label}>{s.framework}</p>
              <h2 className="mt-1 font-serif text-[1.35rem] text-foreground">{s.name}</h2>
              <p className="mt-1 font-serif text-[1.05rem] leading-snug text-accent">{s.investorQuestion}</p>
              <p className="mt-2 text-[0.82rem] text-muted">Evaluates: {s.evaluates.join(" · ")}</p>
              <ul className="mt-3 space-y-2 text-[0.9rem] leading-6 text-foreground">
                {shown.length ? shown.map((o, i) => <li key={i} className="border-l-2 border-gold pl-3"><Cited text={o.text.length > 230 ? `${o.text.slice(0, 229).replace(/\s+\S*$/, "")}…` : o.text} /></li>) : <li className="text-muted">No evidence in the records yet for this framework.</li>}
              </ul>
              <p className="mt-3 text-[0.82rem] text-muted"><span className={label}>Open question </span>{s.openQuestion}</p>
              {s.questions.some((q) => q.status === "approved") ? (
                <p className="mt-2 text-[0.8rem] text-muted"><span className={label}>Supported by </span>{s.questions.filter((q) => q.status === "approved").slice(0, 3).map((q, i) => <span key={q.id}>{i ? " · " : ""}<Link href={q.href} className="text-accent hover:underline">{q.title}</Link></span>)}</p>
              ) : null}
              <p className="mt-2 text-[0.78rem] text-muted">{have} of {s.lenses.length} lenses have some evidence</p>
              <Link href={panelRoute(panel.slug, s.id)} className="mt-4 inline-block text-[0.9rem] text-accent underline-offset-4 hover:underline">Explore {s.name.split(" ").slice(-1)[0]}’s perspective →</Link>
            </li>
          );
        })}
      </ul>
      <details className="mt-8 rounded-[18px] border border-border bg-surface px-4 py-3">
        <summary className="cursor-pointer text-[0.95rem] font-medium text-foreground">Question coverage by specialist</summary>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[520px] text-left text-[0.85rem]">
            <thead><tr className={label}><th className="py-2 pr-3">Specialist</th><th className="pr-3">Mapped questions</th><th className="pr-3">Approved and usable</th><th>Proposed (not in the catalog)</th></tr></thead>
            <tbody>
              {panel.specialists.map((s) => (
                <tr key={s.id} className="border-t border-border"><td className="py-2 pr-3 text-foreground">{s.name}</td><td className="pr-3">{s.questions.length}</td><td className="pr-3">{s.questions.filter((q) => q.status === "approved").length}</td><td>{s.proposed.length}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
      <p className="mt-6 text-[0.78rem] leading-5 text-muted">{PROVENANCE}</p>
    </CockpitShell>
  );
}

export function SpecialistPage({ panel, s }: { panel: Panel; s: SpecialistView }) {
  return (
    <CockpitShell slug={panel.slug} company={panel.company} available={panel.available} docs={panel.docs} titles={panel.titles} panel>
      <PanelNav slug={panel.slug} active={s.id} />
      <p className={`${label} mt-6`}>{s.name} · {s.framework}</p>
      <h1 className="mt-2 font-serif text-[1.9rem] leading-tight text-foreground sm:text-[2.3rem]">{s.coreQuestion}</h1>
      <p className="mt-2 text-[0.88rem] text-muted">{panel.company} · evaluates {s.evaluates.join(" · ").toLowerCase()}.</p>
      <div className="mt-4"><LensChips s={s} /></div>

      <section className="mt-10" aria-label="What the evidence indicates">
        <h2 className="font-serif text-[1.5rem] text-foreground">What the evidence indicates</h2>
        {s.observations.length ? <ul className="mt-4 space-y-3">{s.observations.map((o, i) => <ObsCard key={i} o={o} />)}</ul> : <p className="mt-3 text-[0.92rem] text-muted">The records hold no usable evidence for this framework for {panel.company}. See what remains uncertain below.</p>}
      </section>

      <section className="mt-10" aria-label="Questions to investigate">
        <h2 className="font-serif text-[1.5rem] text-foreground">Questions to investigate</h2>
        <p className="mt-1 text-[0.88rem] text-muted">Catalog questions that bear on this framework. Each opens the shared question page; those without an approved answer say so and are not presented as answered.</p>
        <ul className="mt-4 space-y-2">
          {s.questions.map((q) => (
            <li key={q.id} className={`rounded-[18px] p-4 ${q.status === "approved" ? "border border-border bg-surface" : "border border-dashed border-border"}`}>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <Link href={q.href} className={`font-medium underline-offset-4 hover:underline ${q.status === "approved" ? "text-accent" : "text-foreground"}`}>{q.title}</Link>
                <span className={`text-[0.72rem] ${q.status === "approved" ? "text-accent" : "text-muted"}`}>{q.status === "approved" ? "Approved answer" : "Answer not yet available"}</span>
              </div>
              <p className="mt-1 text-[0.84rem] text-muted">{q.why}</p>
              {q.preview ? <p className="mt-2 border-l-2 border-gold pl-3 text-[0.88rem] leading-6 text-foreground"><Cited text={q.preview} /></p> : null}
            </li>
          ))}
        </ul>
        <details className="mt-4 rounded-[18px] border border-border bg-surface px-4 py-3">
          <summary className="cursor-pointer text-[0.92rem] font-medium text-foreground">Questions this framework needs that the catalog does not yet contain</summary>
          <ul className="mt-3 space-y-3 text-[0.88rem]">
            {s.proposed.map((q) => <li key={q.id}><strong className="text-foreground">{q.title}</strong><span className="block text-muted">{q.why} <em>Needs:</em> {q.needs}</span></li>)}
          </ul>
          <p className="mt-3 text-[0.78rem] text-muted">Definitions only — no answers exist for these, and none is shown as one.</p>
        </details>
      </section>

      <section className="mt-10" aria-label="What remains uncertain">
        <h2 className="font-serif text-[1.5rem] text-foreground">What remains uncertain</h2>
        <ul className="mt-4 space-y-2">
          {s.uncertain.map((g, i) => (
            <li key={i} className="rounded-[18px] border border-dashed border-gold bg-surface p-4">
              <span className="rounded-full bg-gold-soft px-2.5 py-0.5 text-[0.7rem] font-medium text-[#6f5320]">{g.kind}</span>
              <p className="mt-2 text-[0.92rem] leading-6 text-foreground">{g.text}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-10 rounded-[24px] bg-gold-soft/70 p-5" aria-label="Investor takeaway">
        <h2 className="font-serif text-[1.4rem] text-foreground">Investor takeaway</h2>
        <p className="mt-2 text-[1rem] leading-7 text-foreground">{s.takeaway}</p>
      </section>
      <p className="mt-6 text-[0.78rem] leading-5 text-muted">{PROVENANCE}</p>
      <p className="mt-4 text-[0.85rem]"><Link href={panelRoute(panel.slug)} className="text-accent hover:underline">← All five perspectives</Link></p>
    </CockpitShell>
  );
}
