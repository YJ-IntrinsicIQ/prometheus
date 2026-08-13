import { prepareJourneyDescriptionForDisplay } from "@/src/lib/ask-intrinsiciq/presentation";
import type { BusinessJourney } from "@/src/types";

type BusinessJourneyTimelineProps = {
  journey: BusinessJourney;
};

export function BusinessJourneyTimeline({
  journey,
}: BusinessJourneyTimelineProps) {
  const stages = journey.stages.slice(0, 4);
  const useHorizontal = stages.length <= 3;

  return (
    <section className="rounded-[26px] border border-border bg-[rgba(255,255,255,0.44)] p-5 shadow-[0_14px_34px_rgba(15,23,42,0.04)] md:p-6">
      <div>
        <p className="text-[0.7rem] uppercase tracking-[0.1em] text-muted">
          Business journey
        </p>
        <h2 className="mt-1 text-[1.3rem] font-semibold tracking-[-0.01em] text-foreground md:text-[1.45rem]">
          How the business developed
        </h2>
      </div>

      <div
        data-testid="business-journey-grid"
        className={`relative mt-5 grid gap-3 ${
          useHorizontal
            ? "sm:grid-cols-2 xl:grid-cols-3"
            : "sm:grid-cols-2 xl:grid-cols-3"
        }`}
      >
        <div className="absolute bottom-2 left-[0.95rem] top-2 w-px bg-border/70 md:hidden" />
        {stages.map((stage, index) => (
          <article
            key={stage.id}
            className={`relative rounded-[20px] border border-border bg-[rgba(255,255,255,0.88)] px-4 py-4 shadow-[0_10px_24px_rgba(15,23,42,0.04)] ${
              stages.length === 3 && index === 2 ? "sm:col-span-2 xl:col-span-1" : ""
            }`}
          >
            <div className="flex items-start gap-3">
              <span className="inline-flex shrink-0 rounded-full border border-[rgba(74,109,94,0.18)] bg-[rgba(74,109,94,0.08)] px-2.5 py-1 text-[0.72rem] font-medium text-accent">
                {stage.periodLabel}
              </span>
              <div className="min-w-0">
                <h3 className="text-[1rem] font-semibold leading-6 text-foreground">
                  {stage.title}
                </h3>
                <p className="mt-1 text-[0.92rem] leading-6 text-muted">
                  {prepareJourneyDescriptionForDisplay(stage.simpleDescription)}
                </p>
              </div>
            </div>
          </article>
        ))}
      </div>

      {journey.currentDirection ? (
        <div data-testid="business-journey-direction" className="mt-5 rounded-[18px] border border-[rgba(100,116,139,0.2)] bg-[rgba(148,163,184,0.08)] px-4 py-3">
          <p className="text-[0.82rem] font-medium text-muted">Stated direction</p>
          <p className="mt-1 text-[0.92rem] leading-6 text-foreground">
            {journey.currentDirection}
          </p>
        </div>
      ) : null}
    </section>
  );
}
