"use client";

import { Cited } from "./evidence";
import Link from "next/link";
import { questionOfHref, RelatedInline } from "./related-questions";
import { useState, type ReactNode } from "react";
import type { Category, Discovery, Trust, Visual } from "@/src/lib/story/discoveries";

const CATEGORY_DOT: Record<Category, string> = {
  "Important changes": "bg-accent",
  "Emerging patterns": "bg-gold",
  "Evidence connections": "bg-foreground/50",
  "Unanswered questions": "border border-muted bg-transparent",
};
const TRUST_TONE: Record<Trust, string> = {
  Observed: "text-accent",
  Derived: "text-[#6f5320]",
  Interpretation: "text-foreground",
  Unknown: "text-muted",
};
const label = "text-[0.72rem] font-semibold uppercase tracking-[0.12em] text-muted";

export function Visual({ v }: { v: Visual }) {
  if (v.kind === "timeline")
    return (
      <ol className="mt-3 space-y-2 border-l border-border pl-4">
        {v.items.map((i) => (
          <li key={i.when + i.text} className="relative text-[0.9rem]">
            <span aria-hidden className="absolute -left-[21px] top-2 h-2 w-2 rounded-full bg-gold" />
            <strong className="mr-2 font-serif text-foreground">{i.when}</strong>
            <span className="text-muted">{i.text}</span>
          </li>
        ))}
      </ol>
    );
  return (
    <div className="mt-3 overflow-x-auto">
      <table className="w-full min-w-[320px] border-collapse text-left text-[0.88rem]">
        <thead>
          <tr>{v.head.map((h) => <th key={h} className="border-b border-border py-2 pr-4 text-[0.72rem] font-semibold uppercase tracking-[0.1em] text-muted">{h}</th>)}</tr>
        </thead>
        <tbody>
          {v.rows.map((r) => (
            <tr key={r.join("|")}>{r.map((c, i) => <td key={i} className={`border-b border-border/60 py-2 pr-4 ${i === 0 ? "text-foreground" : "text-muted"}`}>{c}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mt-5">
      <p className={label}>{title}</p>
      <div className="mt-1.5 text-[0.93rem] leading-6 text-foreground">{children}</div>
    </div>
  );
}

function Detail({ d }: { d: Discovery }) {
  return (
    <div id={`${d.id}-detail`} className="mt-4 border-t border-border pt-2">
      <Block title="What we discovered">{d.discovered}</Block>
      <Visual v={d.visual} />
      <Block title="Supporting evidence">
        <ul className="space-y-2">
          {d.evidence.map((e) => (
            <li key={e.text + e.source}>
              <span className={`mr-2 text-[0.72rem] font-semibold uppercase tracking-wide ${TRUST_TONE[e.trust]}`}>{e.trust}</span>
              {e.text}
              <span className="block text-[0.8rem] text-muted"><Cited text={e.source} /></span>
            </li>
          ))}
        </ul>
      </Block>
      <Block title="Why it matters to an investor">{d.significance}</Block>
      <Block title="What's still unknown">
        <ul className="list-disc space-y-1 pl-5 text-muted">{d.unknown.map((u) => <li key={u}>{u}</li>)}</ul>
      </Block>
      <p className="mt-5 text-[0.78rem] text-muted">Basis: {d.basis}. Observed = in the records · Derived = calculated · Interpretation = a qualified reading · Unknown = not established.</p>
      <p className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[0.85rem]">
        {d.links.map((l) =>
          l.href.startsWith("#") ? (
            <a key={l.href} href={l.href} className="text-accent underline-offset-4 hover:underline">{l.label} →</a>
          ) : (
            <Link key={l.href} href={l.href} className="text-accent underline-offset-4 hover:underline">Explore in {l.label} →</Link>
          ),
        )}
      </p>
      {(() => { const q = d.links.map((l) => questionOfHref(l.href)).find(Boolean); return q ? <RelatedInline anchor={q} className="mt-2" /> : null; })()}
    </div>
  );
}

export function DiscoveriesSection({ discoveries, title = "Discoveries", intro = "What Prometheus noticed across the filings. Each finding opens to its evidence.", className = "mt-8" }: { discoveries: Discovery[]; title?: string; intro?: string; className?: string }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const [filter, setFilter] = useState<Category | "All">("All");
  const cats = [...new Set(discoveries.map((d) => d.category))];
  const shown = discoveries.filter((d) => filter === "All" || d.category === filter);
  return (
    <section id="discoveries" className={`${className} scroll-mt-6`}>
      <h2 className="font-serif text-[1.6rem] text-foreground">{title}</h2>
      <p className="mt-1 text-[0.92rem] text-muted">{intro}</p>
      {cats.length > 1 ? (
      <div className="mt-4 flex flex-wrap gap-2 text-[0.82rem]" role="group" aria-label="Filter discoveries">
        {(["All", ...cats] as const).map((c) => (
          <button
            key={c}
            type="button"
            aria-pressed={filter === c}
            onClick={() => setFilter(c)}
            className={`rounded-full border px-3 py-1.5 ${filter === c ? "border-accent bg-accent-soft text-accent" : "border-border bg-surface text-muted"}`}
          >
            {c}{c === "All" ? ` · ${discoveries.length}` : ""}
          </button>
        ))}
      </div>
      ) : null}
      <ul className="mt-5 grid gap-4 sm:grid-cols-2">
        {shown.map((d) => {
          const open = openId === d.id;
          return (
            <li key={d.id} className={`rounded-[24px] border border-border bg-surface p-5 shadow-[var(--shadow)] ${open ? "sm:col-span-2" : ""}`}>
              <p className="flex items-center gap-2 text-[0.74rem] font-semibold uppercase tracking-[0.1em] text-muted">
                <span aria-hidden className={`h-2 w-2 rounded-full ${CATEGORY_DOT[d.category]}`} />
                {d.category} · {d.years}
              </p>
              <h3 className="mt-2 font-serif text-[1.2rem] leading-snug text-foreground">{d.headline}</h3>
              <p className="mt-3 font-serif text-[2rem] leading-none text-accent">{d.keyNumber.value}</p>
              <p className="mt-1 text-[0.82rem] text-muted">{d.keyNumber.label}</p>
              <p className="mt-3 text-[0.92rem] leading-6 text-foreground">{d.why}</p>
              <button
                type="button"
                aria-expanded={open}
                aria-controls={`${d.id}-detail`}
                onClick={() => setOpenId(open ? null : d.id)}
                className="mt-3 text-[0.82rem] text-accent"
              >
                {open ? "Hide evidence" : "Explore the evidence"}
              </button>
              {open ? <Detail d={d} /> : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
