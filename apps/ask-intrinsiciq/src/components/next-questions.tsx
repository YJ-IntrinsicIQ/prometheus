import Link from "next/link";
import type { NextQuestion } from "@/src/types";

type NextQuestionsProps = {
  questions: Array<NextQuestion & { href: string; categoryTitle?: string }>;
  exploreHref: string;
};

export function NextQuestions({ questions, exploreHref }: NextQuestionsProps) {
  return (
    <section
      data-testid="next-questions-section"
      className="rounded-[24px] border border-border bg-[rgba(255,255,255,0.42)] p-5 md:p-6"
    >
      <div>
        <p className="text-[0.7rem] uppercase tracking-[0.1em] text-muted">
          Continue researching
        </p>
        <h2 className="mt-2 text-[1.35rem] font-semibold tracking-[-0.01em] text-foreground">
          What to explore next
        </h2>
      </div>
      <div data-testid="next-question-grid" className="mt-5 grid gap-4 lg:grid-cols-3">
        {questions.map((question) => (
          <Link
            key={question.questionId}
            href={question.href}
            data-testid="next-question-card"
            className="group relative flex min-h-[118px] flex-col rounded-[20px] border border-border bg-[rgba(255,255,255,0.88)] px-5 py-5 pr-12 text-left transition hover:border-accent hover:shadow-[0_10px_24px_rgba(15,23,42,0.05)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            <div className="min-w-0">
              {question.categoryTitle ? (
                <p className="text-[0.72rem] uppercase tracking-[0.1em] text-muted">
                  {question.categoryTitle}
                </p>
              ) : null}
              <p className="text-[0.95rem] font-medium leading-6 text-foreground">
                {question.title}
              </p>
            </div>
            <span
              data-testid="next-question-arrow"
              className="absolute bottom-5 right-5 text-accent transition group-hover:translate-x-0.5 group-focus-visible:translate-x-0.5"
            >
              →
            </span>
          </Link>
        ))}
      </div>
      <Link
        href={exploreHref}
        className="mt-5 inline-flex items-center gap-2 text-sm text-muted underline decoration-border underline-offset-4 transition hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        Explore another category <span aria-hidden="true">↗</span>
      </Link>
    </section>
  );
}
