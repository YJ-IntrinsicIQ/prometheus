import Link from "next/link";
import type { StageSummary } from "@/src/lib/catalog/load-explorer";

const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? "" : "s"}`;

/** The research journey for one company: five stages, each showing how much certified intelligence it holds and where to start. */
export function JourneyStrip({ slug, stages, currentStage, className = "mt-6" }: { slug: string; stages: StageSummary[]; currentStage?: string; className?: string }) {
  return (
    <nav aria-label="Research journey" className={className}>
      <p className="text-[0.72rem] font-semibold uppercase tracking-[0.12em] text-muted">Your research path</p>
      <ol className="mt-2 grid gap-2 sm:grid-cols-5">
        {stages.map((s, i) => {
          const href = s.panel ? `/company/${slug}/panel` : s.start?.href ?? `/company/${slug}/questions`;
          const here = s.label === currentStage || s.id === currentStage;
          return (
            <li key={s.id}>
              <Link href={href} aria-current={here ? "step" : undefined} className={`flex h-full flex-col rounded-[16px] border px-3 py-2.5 ${here ? "border-accent bg-accent-soft" : "border-border bg-surface hover:border-accent/60"}`}>
                <span className="text-[0.7rem] text-muted">Step {i + 1}</span>
                <span className="font-serif text-[0.98rem] leading-snug text-foreground">{s.label}</span>
                <span className="mt-1 text-[0.76rem] leading-4 text-muted">
                  {s.panel ? "Five specialist perspectives" : s.approved ? plural(s.approved, "certified answer") : "Answers pending"}
                </span>
              </Link>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
