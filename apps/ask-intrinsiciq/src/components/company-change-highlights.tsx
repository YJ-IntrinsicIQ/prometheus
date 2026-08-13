import Link from "next/link";
import { questionRoute } from "@/src/lib/routes";
import type { ResearchAnswerCard } from "@/src/types";
import { cleanPublicText } from "@/src/lib/ask-intrinsiciq/presentation";

type CompanyChangeHighlightsProps = {
  companySlug: string;
  highlights: Array<{
    questionId: string;
    title: string;
    label: string;
    summary: string;
    followUp: string;
    impact: string;
  }>;
};

export function CompanyChangeHighlights({
  companySlug,
  highlights,
}: CompanyChangeHighlightsProps) {
  if (highlights.length === 0) {
    return null;
  }

  return (
    <section className="rounded-[28px] border border-[rgba(74,109,94,0.16)] bg-[linear-gradient(180deg,rgba(255,255,255,0.92),rgba(247,250,248,0.78))] p-5 shadow-[0_14px_34px_rgba(15,23,42,0.04)] md:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[0.7rem] uppercase tracking-[0.12em] text-muted">
            How the business is changing
          </p>
          <h2 className="mt-1 text-[1.2rem] font-semibold tracking-[-0.01em] text-foreground md:text-[1.35rem]">
            Three material changes worth following
          </h2>
        </div>
        <span className="rounded-full border border-[rgba(74,109,94,0.18)] bg-[rgba(74,109,94,0.08)] px-3 py-1 text-[0.72rem] font-medium uppercase tracking-[0.12em] text-accent">
          Curated questions
        </span>
      </div>

      <div className="mt-5 grid gap-3 lg:grid-cols-3">
        {highlights.slice(0, 3).map((item) => (
          <Link
            key={item.questionId}
            href={questionRoute(companySlug, item.questionId)}
            className="rounded-[22px] border border-border bg-[rgba(255,255,255,0.88)] px-4 py-4 transition hover:border-accent hover:shadow-[0_10px_24px_rgba(20,33,61,0.05)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[0.72rem] uppercase tracking-[0.1em] text-muted">
                  {item.label}
                </p>
                <h3 className="mt-2 text-[1rem] font-medium text-foreground">
                  {item.title}
                </h3>
              </div>
              <span className="rounded-full border border-[rgba(74,109,94,0.16)] bg-[rgba(74,109,94,0.06)] px-2.5 py-1 text-[0.68rem] uppercase tracking-[0.08em] text-accent">
                {item.impact}
              </span>
            </div>
            <p className="mt-3 text-[0.93rem] leading-6 text-foreground">
              {item.summary}
            </p>
            <p className="mt-2 text-[0.88rem] leading-6 text-muted">
              {item.followUp}
            </p>
          </Link>
        ))}
      </div>
    </section>
  );
}

type HighlightSource = {
  questionId: string;
  title: string;
  label: string;
  answer: ResearchAnswerCard | null;
};

export function buildCompanyChangeHighlights(
  sources: HighlightSource[],
): CompanyChangeHighlightsProps["highlights"] {
  return sources
    .map((source) => {
      const interpretation = source.answer?.interpretation;
      if (!interpretation) {
        return null;
      }

      return {
        questionId: source.questionId,
        title: source.title,
        label: source.label,
        summary: cleanPublicText(
          interpretation.conclusion ||
            source.answer?.simpleAnswer ||
            source.answer?.whyItMatters ||
            "",
        ),
        followUp: cleanPublicText(
          interpretation.whatToWatch[0] ||
            interpretation.unresolved[0] ||
            interpretation.whyItMatters ||
            "",
        ),
        impact: labelForImpact(interpretation.thesisImpact),
      };
    })
    .filter(
      (item): item is CompanyChangeHighlightsProps["highlights"][number] =>
        Boolean(item && item.summary && item.followUp),
    );
}

function labelForImpact(value: string) {
  switch (value) {
    case "strengthens":
      return "Strengthens";
    case "weakens":
      return "Weakens";
    case "mixed":
      return "Mixed";
    case "neutral":
      return "Neutral";
    case "unresolved":
      return "Unresolved";
    default:
      return "Mixed";
  }
}
