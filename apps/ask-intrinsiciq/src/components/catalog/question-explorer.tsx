"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { Explorer } from "@/src/lib/catalog/load-explorer";
import { CockpitShell } from "@/src/components/story/cockpit-shell";
import { SPECIALISTS } from "@/src/lib/panel/specialists";
import { stageOfFamily } from "@/src/lib/catalog/journey";
import { JourneyStrip } from "./journey-strip";

const label = "text-[0.72rem] font-semibold uppercase tracking-[0.12em] text-muted";
type Filter = "all" | "approved" | "pending";

export function QuestionExplorer({ data }: { data: Explorer }) {
  const [text, setText] = useState("");
  const [status, setStatus] = useState<Filter>("all");
  const [family, setFamily] = useState<string>("all");
  const needle = text.trim().toLowerCase();
  const families = useMemo(
    () => data.families
      .filter((f) => family === "all" || f.id === family)
      .map((f) => ({ ...f, shown: f.questions.filter((q) => (status === "all" || q.status === status) && (!needle || `${q.title} ${q.shortLabel} ${q.drawsOn.join(" ")}`.toLowerCase().includes(needle))) }))
      .filter((f) => f.shown.length),
    [data, text, status, family, needle],
  );
  const shownCount = families.reduce((n, f) => n + f.shown.length, 0);
  const seg = (on: boolean) => `rounded-full border px-3 py-1.5 text-[0.82rem] ${on ? "border-accent bg-accent-soft text-accent" : "border-border bg-surface text-muted hover:text-accent"}`;
  return (
    <CockpitShell slug={data.slug} company={data.company} available={data.available} docs={data.docs} titles={data.titles}>
      <h1 className="mt-6 font-serif text-[2.1rem] leading-tight text-foreground sm:text-[2.6rem]">{data.company}: All questions</h1>
      <p className="mt-2 max-w-2xl text-[0.95rem] leading-7 text-muted">
        Every question Prometheus supports, by research area. <strong className="text-foreground">{data.totals.approved} of {data.totals.questions}</strong> have a certified answer for {data.company}; the rest are supported but their answers await evidence validation and certification, and none is shown until it passes.
      </p>

      <JourneyStrip slug={data.slug} stages={data.stages} />

      <div className="mt-6 space-y-3">
        <label className="block">
          <span className="sr-only">Search questions</span>
          <input type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="Search questions, e.g. “cash”, “risk”, “promised”" className="w-full rounded-[16px] border border-border bg-surface px-4 py-3 text-[0.95rem] text-foreground outline-none focus-visible:border-accent" />
        </label>
        <div role="group" aria-label="Filter by availability" className="flex flex-wrap gap-2">
          {([["all", `All (${data.totals.questions})`], ["approved", `Certified answer (${data.totals.approved})`], ["pending", `Answer pending (${data.totals.pending})`]] as [Filter, string][]).map(([k, t]) => (
            <button key={k} type="button" aria-pressed={status === k} onClick={() => setStatus(k)} className={seg(status === k)}>{t}</button>
          ))}
        </div>
        <div role="group" aria-label="Filter by research area" className="flex flex-wrap gap-2">
          <button type="button" aria-pressed={family === "all"} onClick={() => setFamily("all")} className={seg(family === "all")}>All areas</button>
          {data.families.map((f) => <button key={f.id} type="button" aria-pressed={family === f.id} onClick={() => setFamily(f.id)} className={seg(family === f.id)}>{f.title}</button>)}
        </div>
      </div>
      <p className="mt-4 text-[0.82rem] text-muted" aria-live="polite">{shownCount} {shownCount === 1 ? "question" : "questions"} shown</p>

      {families.map((f) => (
        <section key={f.id} id={f.id} className="mt-8 scroll-mt-6" aria-label={f.title}>
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-serif text-[1.5rem] text-foreground">{f.title}</h2>
            <span className="text-[0.8rem] text-muted">{stageOfFamily(f.id)?.label ? `${stageOfFamily(f.id)!.label} · ` : ""}{f.approved} of {f.questions.length} certified</span>
          </div>
          {f.description ? <p className="mt-1 text-[0.9rem] leading-6 text-muted">{f.description}</p> : null}
          <ul className="mt-3 space-y-2">
            {f.shown.map((q) => (
              <li key={q.id} className={`rounded-[18px] p-4 ${q.status === "approved" ? "border border-border bg-surface" : "border border-dashed border-border"}`}>
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <Link href={q.href} className={`font-medium underline-offset-4 hover:underline ${q.status === "approved" ? "text-accent" : "text-foreground"}`}>{q.title}</Link>
                  <span className={`rounded-full px-2.5 py-0.5 text-[0.7rem] font-medium ${q.status === "approved" ? "bg-accent-soft text-accent" : "border border-dashed border-border text-muted"}`}>{q.status === "approved" ? "Certified answer" : "Answer pending"}</span>
                </div>
                {q.status === "approved" && q.preview ? (
                  <p className="mt-2 border-l-2 border-gold pl-3 text-[0.9rem] leading-6 text-foreground"><span className="sr-only">What you will learn: </span>{q.preview}</p>
                ) : null}
                <p className="mt-1 text-[0.82rem] leading-5 text-muted">
                  {q.drawsOn.length ? `Draws on ${q.drawsOn.slice(0, 4).join(", ")}${q.drawsOn.length > 4 ? "…" : ""}. ` : ""}{q.basis}.
                </p>
                {q.specialists.length ? (
                  <p className="mt-1 text-[0.78rem] text-muted"><span className={label}>Panel </span>{q.specialists.map((id, i) => <span key={id}>{i ? " · " : ""}<Link href={`/company/${data.slug}/panel/${id}`} className="text-accent hover:underline">{SPECIALISTS.find((s) => s.id === id)!.name.split(" ").slice(-1)[0]}</Link></span>)}</p>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ))}
      {!families.length ? <p className="mt-8 rounded-[18px] border border-dashed border-border p-4 text-[0.92rem] text-muted">No question matches. Clear the search or filters to see all {data.totals.questions} questions.</p> : null}
    </CockpitShell>
  );
}
