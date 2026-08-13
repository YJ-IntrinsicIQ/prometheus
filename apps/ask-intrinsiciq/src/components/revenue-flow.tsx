import {
  prepareFlowLabelForDisplay,
  prepareFlowStepForDisplay,
} from "@/src/lib/ask-intrinsiciq/presentation";
import type { ResearchAnswerCard } from "@/src/types";

type RevenueFlowProps = {
  revenueFlow: NonNullable<ResearchAnswerCard["revenueFlow"]>;
};

export function RevenueFlow({ revenueFlow }: RevenueFlowProps) {
  return (
    <section className="rounded-[26px] border border-border bg-[rgba(255,255,255,0.44)] p-5 shadow-[0_14px_34px_rgba(15,23,42,0.04)] md:p-6">
      <div data-testid="wide-section-revenue-flow" />
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-[0.7rem] uppercase tracking-[0.1em] text-muted">
            Revenue flow
          </p>
          <h2 className="mt-1 text-[1.3rem] font-semibold tracking-[-0.01em] text-foreground md:text-[1.45rem]">
            How the revenue path works
          </h2>
        </div>
        {revenueFlow.evidenceStatus === "partial" ? (
          <span className="inline-flex items-center gap-2 rounded-full border border-[rgba(74,109,94,0.18)] bg-[rgba(74,109,94,0.08)] px-3 py-1 text-[0.72rem] text-accent">
            <span className="h-1.5 w-1.5 rounded-full bg-accent" />
            Partial evidence
          </span>
        ) : null}
      </div>

      <div className="relative mt-6">
        <div className="absolute bottom-2 left-[0.86rem] top-2 w-px bg-[rgba(74,109,94,0.22)] md:bottom-auto md:left-6 md:right-6 md:top-[2.7rem] md:h-px md:w-auto" />
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {revenueFlow.steps.slice(0, 6).map((step, index) => {
            const label = prepareFlowLabelForDisplay(step.label);
            const explanation = prepareFlowStepForDisplay(step.explanation);
            const isMilestone = index === 4;

            return (
              <article
                key={`${step.order}-${step.label}`}
                className="relative rounded-[20px] border border-border bg-[rgba(255,255,255,0.9)] px-4 py-4 shadow-[0_10px_24px_rgba(15,23,42,0.04)]"
              >
                <div className="flex items-start gap-3">
                  <span
                    className={`mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-[0.78rem] font-semibold ${
                      isMilestone
                        ? "border-[rgba(168,131,63,0.32)] bg-[rgba(168,131,63,0.1)] text-gold"
                        : "border-[rgba(74,109,94,0.2)] bg-[rgba(74,109,94,0.08)] text-accent"
                    }`}
                  >
                    {step.order}
                  </span>
                  <div className="min-w-0">
                    <p className="text-[0.98rem] font-semibold leading-6 text-foreground">
                      {label}
                    </p>
                    <p
                      className="mt-1 text-[0.9rem] leading-6 text-muted"
                    >
                      {explanation}
                    </p>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      </div>

      {revenueFlow.offeringExamples && revenueFlow.offeringExamples.length > 0 ? (
        <div className="mt-5">
          <p className="text-[0.82rem] font-medium text-muted">
            Visible offering examples
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {revenueFlow.offeringExamples.slice(0, 3).map((example) => (
              <span
                key={example}
                className="rounded-full border border-border bg-white/78 px-3 py-1.5 text-[0.78rem] text-muted"
              >
                {example}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      <div className="mt-5 grid gap-3 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
        <div className="rounded-[18px] border border-[rgba(74,109,94,0.16)] bg-[rgba(74,109,94,0.06)] px-4 py-3">
          <p className="text-[0.82rem] font-medium text-muted">Cash timing</p>
          <p className="mt-1 text-[0.92rem] leading-6 text-foreground">
            {revenueFlow.cashTimingNote}
          </p>
        </div>
        <div className="rounded-[18px] border border-[rgba(168,131,63,0.18)] bg-[rgba(168,131,63,0.08)] px-4 py-3">
          <p className="text-[0.82rem] font-medium text-muted">Working capital note</p>
          <p className="mt-1 text-[0.92rem] leading-6 text-foreground">
            {revenueFlow.workingCapitalNote}
          </p>
        </div>
      </div>
    </section>
  );
}
