"use client";

import { Fragment, useState, type ReactNode } from "react";
import { CockpitShell, Unavailable } from "./cockpit-shell";
import { Cited } from "./evidence";
import { CommitmentStatesList, CommitmentsSection } from "./commitment-section";
import { DiscoveriesSection } from "./discoveries-section";
import { ConnectionsSection } from "./connections-section";
import { PromiseChains, Scorecard } from "./accountability-section";
import type { Story, StoryCategory, StoryEvent } from "@/src/lib/story/story-adapter";
import type { StageSummary } from "@/src/lib/catalog/load-explorer";
import { JourneyStrip } from "@/src/components/catalog/journey-strip";

const CATEGORY_STYLE: Record<StoryCategory, string> = {
  Strategy: "bg-gold-soft text-[#6f5320]",
  Investment: "bg-accent-soft text-accent",
  Execution: "bg-surface-strong text-foreground",
  Outcome: "bg-foreground text-surface",
  Risk: "bg-[#f3dcd6] text-[#7a4036]",
};

const HIGHLIGHT =
  /(₹[\d,.]+ cr|USD [\d.,]+(?: billion)?|\d+(?:\.\d+)?%|H[12] 20\d{2}|(?:January|February|March|April|May|June|July|August|September|October|November|December) (?:\d{1,2}, )?20\d{2}|\d{1,2} March 20\d{2}|FY\d{2})/g;

export function highlight(text: string): ReactNode {
  return text.split(HIGHLIGHT).map((part, i) =>
    i % 2 ? <strong key={i} className="font-semibold text-foreground">{part}</strong> : <Fragment key={i}>{part}</Fragment>,
  );
}

function Chip({ className, children }: { className: string; children: ReactNode }) {
  return <span className={`rounded-full px-2.5 py-1 text-[0.72rem] font-medium tracking-wide ${className}`}>{children}</span>;
}

function EventCard({ event, open, onToggle }: { event: StoryEvent; open: boolean; onToggle: () => void }) {
  const panelId = `${event.id}-panel`;
  const trim = (t: string) => t.replace(/…$/, "").trim();
  // The summary is shown only when it adds something beyond the headline.
  const showSummary = !(trim(event.summary).length <= trim(event.headline).length + 8 && trim(event.summary).startsWith(trim(event.headline).slice(0, 40)));
  const truncated = !!event.original && (event.headline.endsWith("…") || event.original.length > event.headline.length + 2);
  const happened = event.interpretation.happened === event.summary || (event.original && event.interpretation.happened.includes(event.original)) ? null : event.interpretation.happened;
  return (
    <li id={event.id} className="relative scroll-mt-6 pl-8 sm:pl-10">
      <span aria-hidden className="absolute left-[7px] top-6 h-3 w-3 rounded-full border-2 border-gold bg-background sm:left-[11px]" />
      <div className="rounded-[24px] border border-border bg-surface shadow-[var(--shadow)]">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={onToggle}
          className="group relative w-full rounded-[24px] p-5 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
        >
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-serif text-[1.15rem] text-foreground">{event.period}</span>
            <Chip className={CATEGORY_STYLE[event.category]}>{event.category}</Chip>
            <Chip className="border border-border text-muted">{event.kind}</Chip>
          </div>
          <h3 className="mt-3 font-serif text-[1.2rem] leading-snug text-foreground">{event.headline}</h3>
          {truncated ? (
            <span role="tooltip" className="pointer-events-none absolute inset-x-4 bottom-3 z-10 hidden rounded-[14px] border border-border bg-surface p-3 text-[0.85rem] leading-6 text-foreground shadow-[var(--shadow)] group-hover:block group-focus-visible:block">
              {event.original}
            </span>
          ) : null}
          {showSummary ? <p className="mt-2 text-[0.95rem] leading-7 text-muted">{highlight(event.summary)}</p> : null}
          <span className="mt-3 inline-block text-[0.8rem] text-accent">{open ? "Hide evidence" : "Show evidence"}</span>
        </button>
        {open ? (
          <div id={panelId} className="space-y-5 border-t border-border p-5">
            {event.original && (truncated || event.original !== event.summary) ? (
              <div>
                <p className="text-[0.72rem] font-semibold uppercase tracking-[0.12em] text-muted">Original wording</p>
                <p className="mt-1 border-l-2 border-gold pl-3 text-[0.92rem] leading-6 text-foreground">{event.original}</p>
              </div>
            ) : null}
            <dl className={`grid gap-4 ${happened ? "sm:grid-cols-3" : "sm:grid-cols-2"}`}>
              {[
                ...(happened ? [["What happened", happened]] : []),
                ["Why it could matter", event.interpretation.matters],
                ["What remains unproven", event.interpretation.unproven],
              ].map(([label, text]) => (
                <div key={label}>
                  <dt className="text-[0.72rem] font-semibold uppercase tracking-[0.12em] text-muted">{label}</dt>
                  <dd className="mt-1 text-[0.92rem] leading-6 text-foreground">{highlight(text)}</dd>
                </div>
              ))}
            </dl>
            {event.commitment ? (
              <div>
                <p className="text-[0.72rem] font-semibold uppercase tracking-[0.12em] text-muted">Tracker versus evidence</p>
                <CommitmentStatesList s={event.commitment} className="mt-2" />
              </div>
            ) : null}
            <div>
              <p className="text-[0.72rem] font-semibold uppercase tracking-[0.12em] text-muted">Evidence</p>
              <ul className="mt-1 list-disc space-y-1 pl-5 text-[0.9rem] text-foreground">
                {event.evidence.map((e) => <li key={e}><Cited text={e} /></li>)}
              </ul>
            </div>
            {event.related.length ? (
              <div>
                <p className="text-[0.72rem] font-semibold uppercase tracking-[0.12em] text-muted">Connected events</p>
                <ul className="mt-1 space-y-1 text-[0.9rem]">
                  {event.related.map((r) => (
                    <li key={r.id}><a href={`#${r.id}`} className="text-accent underline-offset-4 hover:underline">{r.label}</a> <span className="text-muted">— {r.note}</span></li>
                  ))}
                </ul>
              </div>
            ) : null}
            {event.limitations.length ? (
              <div>
                <p className="text-[0.72rem] font-semibold uppercase tracking-[0.12em] text-muted">Limitations</p>
                <ul className="mt-1 list-disc space-y-1 pl-5 text-[0.9rem] text-muted">
                  {event.limitations.map((l) => <li key={l}>{l}</li>)}
                </ul>
              </div>
            ) : null}
            <p className="text-[0.78rem] text-muted">Source: approved records. Linked citations open the filing at that page; other citations are shown as text.</p>
          </div>
        ) : null}
      </div>
    </li>
  );
}

export function StoryView({ story, journey }: { story: Story; journey?: StageSummary[] }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const shown = story.events.filter((e) => showAll || e.initial);
  const hidden = story.events.length - story.events.filter((e) => e.initial).length;

  return (
    <CockpitShell slug={story.slug} company={story.company} available={story.available} docs={story.docs} titles={story.titles}>
      <h1 className="mt-6 font-serif text-[2.1rem] leading-tight text-foreground sm:text-[2.6rem]">
        {story.company}: The Story
      </h1>
      {story.cutoff ? <p className="mt-2 text-[0.88rem] text-muted">{story.cutoff}. Nothing outside the available documents is included.</p> : null}

      {journey ? <JourneyStrip slug={story.slug} stages={journey} /> : null}

      {story.discoveries.length ? <DiscoveriesSection discoveries={story.discoveries} /> : (
        <Unavailable title="Discoveries">No pattern, change or open question could be supported by the available records for {story.company}. Nothing has been added to fill the gap.</Unavailable>
      )}

      {(() => {
        // Only explain the kinds of event that actually appear on this page.
        const legend: [string, string][] = [
          ["Management statement", "what management said it would do."],
          ["Confirmed activity", "something the records show was done or reported."],
          ["Reported result", "a figure from the reported financial statements."],
          ["Risk disclosure", "a risk management described, with no claim about its financial effect."],
        ];
        const present = legend.filter(([k]) => story.events.some((e) => e.kind === k));
        return present.length ? (
          <div className={`mt-6 grid gap-2 rounded-[20px] border border-border bg-surface p-4 text-[0.85rem] text-muted ${present.length >= 3 ? "sm:grid-cols-2" : present.length === 2 ? "sm:grid-cols-2" : ""}`}>
            {present.map(([k, v]) => <p key={k}><strong className="text-foreground">{k}</strong> — {v}</p>)}
          </div>
        ) : null;
      })()}

      {story.events.length < 4 ? (
        <p className="mt-8 rounded-[20px] border border-dashed border-border bg-surface p-4 text-[0.9rem] text-muted">
          Limited evidence: the available records support only {story.events.length} timeline {story.events.length === 1 ? "event" : "events"} for {story.company}. Nothing has been added to fill the gap.
        </p>
      ) : null}
      <ol id="timeline" className="relative mt-8 space-y-5 before:absolute before:bottom-2 before:left-[12px] before:top-2 before:w-px before:bg-border sm:before:left-[16px]">
        {shown.map((e) => (
          <EventCard key={e.id} event={e} open={openId === e.id} onToggle={() => setOpenId(openId === e.id ? null : e.id)} />
        ))}
      </ol>

      {hidden > 0 ? (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className="mt-6 rounded-full border border-border bg-surface px-5 py-2 text-[0.9rem] text-foreground"
        >
          {showAll ? "Show fewer events" : `Show ${hidden} more events`}
        </button>
      ) : null}

      <p className="mt-6 text-[0.85rem] text-muted">
        Events are ordered by date. Order in time is not evidence that one event caused another.
      </p>

      {story.connections.length ? <ConnectionsSection connections={story.connections} /> : (
        <Unavailable title="Connections">The records do not link intentions, investments, execution and outcomes for {story.company} closely enough to show a connection. A missing link is not a negative finding.</Unavailable>
      )}

      {story.commitments ? <CommitmentsSection rows={story.commitments} /> : null}
      {story.accountability ? <PromiseChains data={story.accountability} /> : null}

      {story.gaps.length ? (
        <section className="mt-10 rounded-[24px] border border-border bg-surface-strong p-5">
          <h2 className="font-serif text-[1.2rem] text-foreground">What the records do not show</h2>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-[0.92rem] leading-6 text-muted">
            {story.gaps.map((g) => <li key={g}>{g}</li>)}
          </ul>
        </section>
      ) : null}

      {story.accountability ? <Scorecard data={story.accountability} /> : null}

      <p className="mt-8 text-[0.78rem] text-muted">Built from: {story.sources.join(" · ")}.</p>
    </CockpitShell>
  );
}
