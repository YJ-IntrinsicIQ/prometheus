import type { ResearchAnswerCard } from "@/src/types";
import type { InvestorInterpretation, ThesisImpact } from "@/src/types/investor-interpretation";
import type { ProgressionInsight } from "@/src/types/progression";
import { cleanPublicList, cleanPublicText } from "@/src/lib/ask-intrinsiciq/presentation";

type InvestorAnswerStackProps = {
  answer: ResearchAnswerCard;
};

type TimelineStep = {
  period: string;
  label: string;
  description: string;
  whyItMatters: string;
  impact: ProgressionInsight["convictionImpact"] | ThesisImpact;
};

export function InvestorAnswerStack({ answer }: InvestorAnswerStackProps) {
  const interpretation = answer.interpretation;

  if (!interpretation) {
    return null;
  }

  const steps = buildTimelineSteps(answer.progression, interpretation);
  const watchItems = (() => {
    const seen = new Set<string>();
    cleanPublicList([interpretation.conclusion], { seen, limit: 1 });
    cleanPublicList([interpretation.whyItMatters], { seen, limit: 1 });
    cleanPublicList([interpretation.economicMechanism], { seen, limit: 1 });
    cleanPublicList(interpretation.whatChanged, { seen, limit: 3 });
    cleanPublicList(interpretation.positiveEvidence, { seen, limit: 3 });
    cleanPublicList(interpretation.negativeEvidence, { seen, limit: 3 });
    cleanPublicList(interpretation.unresolved, { seen, limit: 3 });
    const primaryWatchItems =
      interpretation.whatToWatch.length > 0
        ? cleanPublicList(interpretation.whatToWatch, { seen, limit: 3 })
        : cleanPublicList(answer.progression?.unresolvedItems ?? [], { seen, limit: 3 });
    return primaryWatchItems;
  })();
  const conclusion = cleanPublicText(interpretation.conclusion);
  const whyItMatters = cleanPublicText(interpretation.whyItMatters);
  const economicMechanism = cleanPublicText(interpretation.economicMechanism);
  const confidenceBasis = cleanPublicList(interpretation.confidence.basis, { limit: 2 });

  return (
    <section className="rounded-[28px] border border-[rgba(74,109,94,0.16)] bg-[linear-gradient(180deg,rgba(255,255,255,0.94),rgba(247,250,248,0.82))] p-5 shadow-[0_14px_34px_rgba(15,23,42,0.04)] md:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[0.7rem] uppercase tracking-[0.12em] text-muted">
            Bottom line
          </p>
          <h2 className="mt-1 text-[1.2rem] font-semibold tracking-[-0.01em] text-foreground md:text-[1.35rem]">
            What the evidence says right now
          </h2>
        </div>
        <span className="rounded-full border border-[rgba(74,109,94,0.18)] bg-[rgba(74,109,94,0.08)] px-3 py-1 text-[0.72rem] font-medium uppercase tracking-[0.12em] text-accent">
          {labelForImpact(interpretation.thesisImpact)}
        </span>
      </div>

      <p className="mt-4 text-[1rem] leading-7 text-foreground">
        {conclusion}
      </p>
      {whyItMatters ? (
        <p className="mt-3 text-[0.95rem] leading-7 text-muted">
          {whyItMatters}
        </p>
      ) : null}

      <div className="mt-5 grid gap-3 md:grid-cols-2">
        <article className="rounded-[20px] border border-border bg-[rgba(255,255,255,0.85)] px-4 py-4">
          <p className="text-[0.72rem] uppercase tracking-[0.1em] text-muted">
            Economic mechanism
          </p>
          <p className="mt-2 text-[0.95rem] leading-7 text-foreground">
            {economicMechanism}
          </p>
        </article>

        <article className="rounded-[20px] border border-border bg-[rgba(255,255,255,0.85)] px-4 py-4">
          <p className="text-[0.72rem] uppercase tracking-[0.1em] text-muted">
            Confidence
          </p>
          <p className="mt-2 text-[0.95rem] leading-7 text-foreground">
            {labelForConfidence(interpretation.confidence.level)}
          </p>
          {confidenceBasis.length > 0 ? (
            <p className="mt-2 text-[0.85rem] leading-6 text-muted">
              Basis: {confidenceBasis.join("; ")}
            </p>
          ) : null}
        </article>
      </div>

      {steps.length > 0 ? (
        <div className="mt-6">
          <p className="text-[0.72rem] uppercase tracking-[0.1em] text-muted">
            Progression
          </p>
          <ol className="relative mt-3 space-y-3 border-l border-[rgba(74,109,94,0.14)] pl-4">
            {steps.map((step, index) => (
              <li key={`${step.period}-${step.label}-${index}`} className="relative">
                <span className="absolute -left-[1.18rem] top-3 h-2.5 w-2.5 rounded-full border border-[rgba(74,109,94,0.34)] bg-[rgba(74,109,94,0.16)]" />
                <article className="rounded-[20px] border border-border bg-[rgba(255,255,255,0.88)] px-4 py-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full border border-[rgba(74,109,94,0.18)] bg-[rgba(74,109,94,0.08)] px-2.5 py-1 text-[0.72rem] font-medium uppercase tracking-[0.08em] text-accent">
                      {step.period || "Current"}
                    </span>
                    <span className="text-[0.78rem] uppercase tracking-[0.08em] text-muted">
                      {step.label}
                    </span>
                    <span className="text-[0.7rem] uppercase tracking-[0.12em] text-muted">
                      {labelForImpact(step.impact)}
                    </span>
                  </div>
                  <p className="mt-2 text-[0.95rem] leading-7 text-foreground">
                    {step.description}
                  </p>
                  {step.whyItMatters ? (
                    <p className="mt-2 text-[0.9rem] leading-6 text-muted">
                      {step.whyItMatters}
                    </p>
                  ) : null}
                </article>
              </li>
            ))}
          </ol>
        </div>
      ) : null}

      <div className="mt-6 grid gap-3 md:grid-cols-2">
        {interpretation.positiveEvidence.length > 0 ? (
          <InsightListCard title="What strengthens the case" items={interpretation.positiveEvidence} />
        ) : null}
        {interpretation.negativeEvidence.length > 0 ? (
          <InsightListCard title="What weakens it" items={interpretation.negativeEvidence} />
        ) : null}
      </div>

      <div className="mt-3 grid gap-3 md:grid-cols-2">
        {interpretation.unresolved.length > 0 ? (
          <InsightListCard title="What remains unproven" items={interpretation.unresolved} tone="neutral" />
        ) : null}
        {watchItems.length > 0 ? (
          <InsightListCard
            title="What to watch"
            items={watchItems}
            tone="watch"
          />
        ) : null}
      </div>
    </section>
  );
}

function buildTimelineSteps(
  progression: ResearchAnswerCard["progression"],
  interpretation: InvestorInterpretation,
): TimelineStep[] {
  if (progression?.turningPoints?.length) {
    return progression.turningPoints.slice(0, 6).map((point) => ({
      period: point.period,
      label: point.label,
      description: point.description,
      whyItMatters: point.whyItMatters,
      impact: point.impact,
    }));
  }
  return [];
}

type InsightListCardProps = {
  title: string;
  items: string[];
  tone?: "default" | "neutral" | "watch";
};

function InsightListCard({ title, items, tone = "default" }: InsightListCardProps) {
  const accentClass =
    tone === "watch"
      ? "border-[rgba(105,92,0,0.16)] bg-[rgba(255,247,214,0.5)]"
      : tone === "neutral"
        ? "border-[rgba(100,116,139,0.14)] bg-[rgba(148,163,184,0.08)]"
        : "border-border bg-[rgba(255,255,255,0.88)]";

  return (
    <article className={`rounded-[20px] border px-4 py-4 ${accentClass}`}>
      <p className="text-[0.72rem] uppercase tracking-[0.1em] text-muted">
        {title}
      </p>
      {items.length > 0 ? (
        <ul className="mt-3 space-y-2">
          {items.slice(0, 3).map((item) => (
            <li key={`${title}-${item}`} className="text-[0.92rem] leading-6 text-foreground">
              {item}
            </li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}

function labelForImpact(value: ProgressionInsight["convictionImpact"] | ThesisImpact) {
  switch (value) {
    case "strengthened":
    case "strengthens":
      return "STRENGTHENS";
    case "weakened":
    case "weakens":
      return "WEAKENS";
    case "mixed":
      return "MIXED";
    case "neutral":
      return "NEUTRAL";
    case "unresolved":
      return "UNRESOLVED";
    case "unchanged":
      return "UNCHANGED";
    default:
      return "UNCLEAR";
  }
}

function labelForConfidence(
  value: InvestorInterpretation["confidence"]["level"],
) {
  switch (value) {
    case "high":
      return "High";
    case "medium":
      return "Medium";
    case "low":
      return "Low";
    default:
      return "Insufficient";
  }
}
