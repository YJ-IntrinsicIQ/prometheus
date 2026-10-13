"use client";

import Link from "next/link";
import { nextInline } from "@/src/lib/catalog/journey";
import { questionRoute } from "@/src/lib/routes";
import { useJourney } from "./evidence";

/** "Continue the research": the questions that follow `anchor`, offered only when their answer is approved for this company. */
export function RelatedInline({ anchor, className = "mt-3" }: { anchor: string; className?: string }) {
  const j = useJourney();
  if (!j?.available || !j.titles) return null;
  const items = nextInline(anchor, j.available, j.titles, 2);
  if (!items.length) return null;
  return (
    <p className={`${className} text-[0.82rem] text-muted`}>
      <span className="font-semibold uppercase tracking-[0.1em]">Then </span>
      {items.map((x, i) => (
        <span key={x.id}>{i ? " · " : ""}<Link href={questionRoute(j.slug, x.id)} title={x.why} className="text-accent underline-offset-4 hover:underline">{x.title}</Link></span>
      ))}
    </p>
  );
}

/** The question id a card already links to, e.g. ".../question/how-is-capital-allocated" -> "how-is-capital-allocated". */
export const questionOfHref = (href: string | undefined) => (href && /\/question\/([a-z0-9-]+)$/.exec(href)?.[1]) || null;
