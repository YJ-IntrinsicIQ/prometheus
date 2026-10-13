"use client";

import { createContext, Fragment, useContext, type ReactNode } from "react";
import { evidenceHref, findCitations } from "@/src/lib/evidence/cite";

type Ctx = { slug: string; company: string; docs: string[]; available?: string[]; titles?: Record<string, string> };
const EvidenceContext = createContext<Ctx | null>(null);

export function EvidenceProvider({ slug, company, docs, available, titles, children }: Ctx & { children: ReactNode }) {
  return <EvidenceContext.Provider value={{ slug, company, docs, available, titles }}>{children}</EvidenceContext.Provider>;
}

/** The company, its approved question ids and their titles, for components that suggest related questions. */
export function useJourney(): Ctx | null {
  return useContext(EvidenceContext);
}

/**
 * Text with its citations made clickable. "Annual report FY26, p.107" opens that filing at that page — but only when
 * the filing exists. Any other citation (no page, a presentation, an unavailable year) stays as plain text.
 */
export function Cited({ text }: { text: string }) {
  const ctx = useContext(EvidenceContext);
  const cites = ctx ? findCitations(text).filter((c) => ctx.docs.includes(c.fy)) : [];
  if (!ctx || cites.length === 0) return <>{text}</>;
  const parts: ReactNode[] = [];
  let at = 0;
  cites.forEach((c, i) => {
    parts.push(<Fragment key={`t${i}`}>{text.slice(at, c.start)}</Fragment>);
    parts.push(
      <a
        key={`c${i}`}
        href={evidenceHref(ctx.slug, c.fy, c.page)}
        target="_blank"
        rel="noopener noreferrer"
        title={`Open ${ctx.company} ${c.fy.toUpperCase()} annual report at page ${c.page}`}
        aria-label={`${text.slice(c.start, c.end)} — open ${ctx.company} ${c.fy.toUpperCase()} annual report at page ${c.page} (new tab)`}
        className="rounded-sm text-accent underline decoration-dotted underline-offset-4 hover:decoration-solid focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
      >
        {text.slice(c.start, c.end)}<span aria-hidden> ↗</span>
      </a>,
    );
    at = c.end;
  });
  parts.push(<Fragment key="tail">{text.slice(at)}</Fragment>);
  return <>{parts}</>;
}
