import { prepareInterpretationForDisplay } from "@/src/lib/ask-intrinsiciq/presentation";
import type { FinancialVisualSummary } from "@/src/types";

type FinancialVisualRendererProps = {
  visuals: FinancialVisualSummary[];
};

export function FinancialVisualRenderer({
  visuals,
}: FinancialVisualRendererProps) {
  if (visuals.length === 0) {
    return null;
  }

  return (
    <section className="rounded-[26px] border border-border bg-[rgba(255,255,255,0.44)] p-5 shadow-[0_14px_34px_rgba(15,23,42,0.04)] md:p-6">
      <div data-testid="wide-section-financial-context" />
      <div>
        <p className="text-[0.7rem] uppercase tracking-[0.1em] text-muted">
          Financial context
        </p>
        <h2 className="mt-1 text-[1.3rem] font-semibold tracking-[-0.01em] text-foreground md:text-[1.45rem]">
          The numbers that shape the answer
        </h2>
      </div>

      <div className="mt-5 space-y-4">
        {visuals.map((visual) => (
          <FinancialVisualCard key={visual.id} visual={visual} />
        ))}
      </div>
    </section>
  );
}

function FinancialVisualCard({
  visual,
}: {
  visual: FinancialVisualSummary;
}) {
  const isWorkingCapital = visual.id === "working_capital_days";
  const isBridge = visual.id === "owner_earnings_bridge";

  return (
    <article className="rounded-[20px] border border-border bg-[rgba(255,255,255,0.88)] px-4 py-4 shadow-[0_10px_24px_rgba(15,23,42,0.04)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-[1rem] font-semibold text-foreground">{visual.title}</h3>
          <p className="mt-1 text-[0.9rem] leading-6 text-muted">{visual.subtitle}</p>
        </div>
        <span className="rounded-full border border-border bg-white/72 px-2.5 py-1 text-[0.72rem] text-muted">
          {visualLabel(visual)}
        </span>
      </div>

      <div className="mt-4">
        {isWorkingCapital ? (
          <WorkingCapitalVisual visual={visual} />
        ) : isBridge ? (
          <BridgeVisual visual={visual} />
        ) : (
          <ComparisonVisual visual={visual} />
        )}
      </div>

      <p className="mt-4 text-[0.9rem] leading-6 text-muted" title={visual.interpretation}>
        {prepareInterpretationForDisplay(visual.interpretation)}
      </p>
      {visual.precisionNote ? (
        <p className="mt-2 text-[0.82rem] leading-6 text-muted">
          {visual.precisionNote}
        </p>
      ) : null}
    </article>
  );
}

function ComparisonVisual({ visual }: { visual: FinancialVisualSummary }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {visual.series.flatMap((series) =>
        series.points.map((point, pointIndex) => (
          <div
            key={`${visual.id}-${series.label}-${point.period}-${pointIndex}`}
            className="rounded-[18px] border border-border bg-white/76 px-4 py-3"
          >
            <p className="text-[0.78rem] text-muted">
              {series.label}
              {point.semanticLabel ? ` · ${point.semanticLabel}` : ""}
            </p>
            <p className="mt-1 text-[0.78rem] text-muted">{point.period}</p>
            <p className="mt-2 text-[1rem] font-semibold text-foreground">
              {point.displayValue}
            </p>
          </div>
        )),
      )}
    </div>
  );
}

function WorkingCapitalVisual({ visual }: { visual: FinancialVisualSummary }) {
  const items = visual.series.flatMap((series) => series.points.map((point) => ({
    label: point.semanticLabel || series.label,
    period: point.period,
    value: point.displayValue,
  })));

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {items.map((item) => (
        <div
          key={`${visual.id}-${item.label}-${item.period}`}
          className="rounded-[18px] border border-border bg-white/76 px-4 py-3"
        >
          <p className="text-[0.78rem] text-muted">{item.label}</p>
          <p className="mt-1 text-[0.78rem] text-muted">{item.period}</p>
          <p className="mt-2 text-[1rem] font-semibold text-foreground">{item.value}</p>
        </div>
      ))}
    </div>
  );
}

function BridgeVisual({ visual }: { visual: FinancialVisualSummary }) {
  const steps = visual.series.flatMap((series) => series.points.map((point) => ({
    label: point.semanticLabel || series.label,
    period: point.period,
    value: point.displayValue,
  })));

  return (
    <div className="grid gap-3 md:grid-cols-3">
      {steps.map((step, index) => (
        <div key={`${visual.id}-${step.label}-${step.period}`} className="relative rounded-[18px] border border-border bg-white/76 px-4 py-3">
          <p className="text-[0.78rem] text-muted">{step.label}</p>
          <p className="mt-1 text-[0.78rem] text-muted">{step.period}</p>
          <p className="mt-2 text-[1rem] font-semibold text-foreground">{step.value}</p>
          {index < steps.length - 1 ? (
            <span className="mt-3 inline-block text-[0.78rem] text-muted">
              {index === 0 ? "− Capex" : "= Owner-oriented cash"}
            </span>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function visualLabel(visual: FinancialVisualSummary) {
  switch (visual.visualType) {
    case "bridge":
      return "Bridge";
    case "comparison":
      return "Comparison";
    case "ratio":
      return "Days view";
    default:
      return "Context card";
  }
}
