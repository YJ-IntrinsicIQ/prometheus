"use client";

import Link from "next/link";
import { questionOfHref, RelatedInline } from "./related-questions";
import { useEffect, useState } from "react";
import { Cited } from "./evidence";
import type { ConnEdge, ConnNode, Connection, Relation } from "@/src/lib/story/connections";

const EDGE: Record<Relation, { line: string; label: string; tone: string }> = {
  Supported: { line: "border-l-2 border-accent", label: "Supported by the records", tone: "text-accent" },
  Related: { line: "border-l-2 border-dashed border-gold", label: "Related observation — link not proven", tone: "text-[#6f5320]" },
  Unverified: { line: "border-l-2 border-dotted border-muted/60", label: "Unverified connection", tone: "text-muted" },
};

function Connector({ edge }: { edge: ConnEdge }) {
  const e = EDGE[edge.relation];
  return (
    <div className="ml-6 py-1">
      <div className={`${e.line} py-3 pl-5`}>
        <p className={`text-[0.78rem] font-semibold ${e.tone}`}>
          {edge.relation === "Unverified" ? "? " : ""}{e.label}
        </p>
        <p className="mt-0.5 text-[0.84rem] leading-5 text-muted">{edge.note}</p>
      </div>
    </div>
  );
}

function Node({ node, index, dim }: { node: ConnNode; index: number; dim: boolean }) {
  const [open, setOpen] = useState(false);
  const id = `${node.title.replace(/\W+/g, "-")}-${index}-src`;
  return (
    <div className={`rounded-[20px] border border-border bg-surface-strong/50 p-4 ${dim ? "opacity-80" : ""}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h4 className="font-serif text-[1.05rem] text-foreground">{node.title}</h4>
        <span className="text-[0.8rem] text-muted">{node.period}</span>
      </div>
      <p className="mt-1 text-[0.92rem] leading-6 text-foreground">{node.establishes}</p>
      {node.facts.length ? (
        <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[0.85rem] text-muted">
          {node.facts.map((f) => <li key={f} className="font-medium text-foreground">{f}</li>)}
        </ul>
      ) : null}
      <button type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen((v) => !v)} className="mt-2 text-[0.78rem] text-accent">
        {open ? "Hide sources" : "Show sources"}
      </button>
      {open ? (
        <div id={id} className="mt-2 border-t border-border pt-2 text-[0.85rem]">
          <ul className="list-disc space-y-1 pl-5">{node.evidence.map((e) => <li key={e}><Cited text={e} /></li>)}</ul>
        </div>
      ) : null}
    </div>
  );
}

export function ConnectionCard({ c }: { c: Connection }) {
  const firstWeak = c.edges.findIndex((e) => e.relation !== "Supported");
  return (
    <li id={c.id} className="scroll-mt-6 rounded-[24px] border border-border bg-surface p-5 shadow-[var(--shadow)] sm:p-6">
      <h3 className="font-serif text-[1.25rem] leading-snug text-foreground">{c.title}</h3>
      <p className="mt-1 text-[0.9rem] text-muted">{c.question}</p>
      <div className="mt-4">
        {c.nodes.map((n, i) => (
          <div key={n.title + i}>
            <Node node={n} index={i} dim={firstWeak !== -1 && i > firstWeak && c.edges[firstWeak].relation === "Unverified"} />
            {c.edges[i] ? <Connector edge={c.edges[i]} /> : null}
          </div>
        ))}
      </div>
      {c.stopNote ? (
        <p className="mt-4 rounded-[14px] bg-gold-soft/70 px-4 py-3 text-[0.88rem] leading-6 text-[#4f3b14]">
          <strong>Where the evidence stops. </strong>{c.stopNote}
        </p>
      ) : null}
      {c.link ? (
        <Link href={c.link.href} className="mt-4 inline-block text-[0.85rem] text-accent underline-offset-4 hover:underline">
          Explore in {c.link.label} →
        </Link>
      ) : null}
      {questionOfHref(c.link?.href) ? <RelatedInline anchor={questionOfHref(c.link?.href)!} className="mt-2" /> : null}
    </li>
  );
}

export function ConnectionsSection({ connections }: { connections: Connection[] }) {
  const [all, setAll] = useState(false);
  useEffect(() => {
    const reveal = () => {
      const i = connections.findIndex((c) => `#${c.id}` === window.location.hash);
      if (i >= 4) {
        setAll(true);
        setTimeout(() => document.getElementById(connections[i].id)?.scrollIntoView(), 0);
      }
    };
    reveal();
    window.addEventListener("hashchange", reveal);
    return () => window.removeEventListener("hashchange", reveal);
  }, [connections]);
  const shown = all ? connections : connections.slice(0, 4);
  return (
    <section id="connections" className="mt-12 scroll-mt-6">
      <h2 className="font-serif text-[1.6rem] text-foreground">Connections</h2>
      <p className="mt-1 text-[0.92rem] text-muted">
        What management said, what it did, what happened, and what value followed — and where the records stop connecting them.
      </p>
      <dl className="mt-4 grid gap-3 rounded-[20px] border border-border bg-surface p-4 text-[0.84rem] text-muted sm:grid-cols-3">
        {(Object.keys(EDGE) as Relation[]).map((r) => (
          <div key={r} className={`${EDGE[r].line} pl-3`}>
            <dt className={`font-semibold ${EDGE[r].tone}`}>{EDGE[r].label}</dt>
            <dd>{r === "Supported" ? "The records identify the same measured item." : r === "Related" ? "Relevant facts; nothing proves one led to the other." : "The records cannot establish the link."}</dd>
          </div>
        ))}
      </dl>
      <ul className="mt-5 space-y-5">{shown.map((c) => <ConnectionCard key={c.id} c={c} />)}</ul>
      {connections.length > 4 ? (
        <button type="button" onClick={() => setAll((v) => !v)} className="mt-5 rounded-full border border-border bg-surface px-5 py-2 text-[0.9rem] text-foreground">
          {all ? "Show fewer connections" : `Show ${connections.length - 4} more connections`}
        </button>
      ) : null}
    </section>
  );
}
