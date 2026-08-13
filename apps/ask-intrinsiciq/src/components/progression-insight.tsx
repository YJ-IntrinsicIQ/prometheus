import type { ProgressionInsight } from "@/src/types/progression";

type ProgressionInsightProps = {
  progression?: ProgressionInsight | null;
};

export function ProgressionInsightCard({ progression }: ProgressionInsightProps) {
  if (!progression) {
    return null;
  }

  return (
    <section className="rounded-[26px] border border-[rgba(74,109,94,0.16)] bg-[linear-gradient(180deg,rgba(255,255,255,0.92),rgba(247,250,248,0.82))] p-5 shadow-[0_14px_34px_rgba(15,23,42,0.04)] md:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[0.7rem] uppercase tracking-[0.1em] text-muted">
            Progression
          </p>
          <h2 className="mt-1 text-[1.3rem] font-semibold tracking-[-0.01em] text-foreground md:text-[1.45rem]">
            How conviction should move with the evidence
          </h2>
        </div>
        <span className="rounded-full border border-[rgba(74,109,94,0.18)] bg-[rgba(74,109,94,0.08)] px-3 py-1 text-[0.72rem] font-medium text-accent">
          {labelForImpact(progression.convictionImpact)}
        </span>
      </div>

      <p className="mt-4 text-[1rem] leading-7 text-foreground">
        {progression.headline}
      </p>
      <p className="mt-3 text-[0.95rem] leading-7 text-muted">
        {progression.whatChanged || progression.currentState}
      </p>

      <div className="mt-5 grid gap-3 md:grid-cols-2">
        <article className="rounded-[20px] border border-border bg-white/80 px-4 py-4">
          <p className="text-[0.72rem] uppercase tracking-[0.1em] text-muted">
            Current state
          </p>
          <p className="mt-2 text-[0.95rem] leading-6 text-foreground">
            {progression.currentState}
          </p>
        </article>
        <article className="rounded-[20px] border border-border bg-white/80 px-4 py-4">
          <p className="text-[0.72rem] uppercase tracking-[0.1em] text-muted">
            Why it changed
          </p>
          <p className="mt-2 text-[0.95rem] leading-6 text-foreground">
            {progression.whyItChanged}
          </p>
        </article>
      </div>

      {progression.latestEvidence.length > 0 ? (
        <div className="mt-5">
          <p className="text-[0.72rem] uppercase tracking-[0.1em] text-muted">
            Latest evidence
          </p>
          <div className="mt-3 grid gap-2">
            {progression.latestEvidence.slice(0, 4).map((item, index) => (
              <div
                key={`${progression.headline}-evidence-${index}`}
                className="rounded-[18px] border border-border bg-[rgba(255,255,255,0.86)] px-4 py-3"
              >
                <p className="text-[0.92rem] leading-6 text-muted">{item}</p>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {progression.unresolvedItems.length > 0 ? (
        <div className="mt-5 rounded-[18px] border border-[rgba(100,116,139,0.14)] bg-[rgba(148,163,184,0.08)] px-4 py-3">
          <p className="text-[0.72rem] uppercase tracking-[0.1em] text-muted">
            Still unresolved
          </p>
          <ul className="mt-2 grid gap-2">
            {progression.unresolvedItems.slice(0, 4).map((item, index) => (
              <li
                key={`${progression.headline}-unresolved-${index}`}
                className="text-[0.92rem] leading-6 text-foreground"
              >
                {item}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

export function TurningPointsList({ progression }: ProgressionInsightProps) {
  const turningPoints = progression?.turningPoints ?? [];

  if (turningPoints.length === 0) {
    return null;
  }

  return (
    <section className="rounded-[26px] border border-border bg-[rgba(255,255,255,0.5)] p-5 shadow-[0_14px_34px_rgba(15,23,42,0.04)] md:p-6">
      <div>
        <p className="text-[0.7rem] uppercase tracking-[0.1em] text-muted">
          Turning points
        </p>
        <h2 className="mt-1 text-[1.2rem] font-semibold tracking-[-0.01em] text-foreground md:text-[1.35rem]">
          What actually moved the story
        </h2>
      </div>

      <div className="mt-5 grid gap-3">
        {turningPoints.slice(0, 4).map((point) => (
          <article
            key={`${point.period}-${point.label}-${point.description}`}
            className="rounded-[20px] border border-border bg-white/85 px-4 py-4"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-[rgba(74,109,94,0.18)] bg-[rgba(74,109,94,0.08)] px-2.5 py-1 text-[0.72rem] font-medium text-accent">
                {point.period || "period unknown"}
              </span>
              <span className="text-[0.78rem] uppercase tracking-[0.08em] text-muted">
                {point.label}
              </span>
            </div>
            <p className="mt-2 text-[0.95rem] leading-6 text-foreground">
              {point.description}
            </p>
            <p className="mt-2 text-[0.9rem] leading-6 text-muted">
              {point.whyItMatters}
            </p>
            <p className="mt-2 text-[0.75rem] uppercase tracking-[0.08em] text-muted">
              Conviction impact: {labelForImpact(point.impact)}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}

function labelForImpact(value: ProgressionInsight["convictionImpact"]) {
  switch (value) {
    case "strengthened":
      return "Conviction strengthened";
    case "weakened":
      return "Conviction weakened";
    case "unchanged":
      return "Conviction unchanged";
    default:
      return "Conviction still uncertain";
  }
}
