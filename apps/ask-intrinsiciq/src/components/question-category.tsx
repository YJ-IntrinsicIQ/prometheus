import { questionRoute } from "@/src/lib/routes";
import { QuestionChip } from "@/src/components/question-chip";
import type { ResearchCategory } from "@/src/types";

type QuestionCategoryProps = {
  companySlug: string;
  category: ResearchCategory;
  isOpen: boolean;
  onOpen: () => void;
  progressText?: string | null;
};

export function QuestionCategory({
  companySlug,
  category,
  isOpen,
  onOpen,
  progressText,
}: QuestionCategoryProps) {
  return (
    <section className="rounded-[24px] border border-border bg-[rgba(255,255,255,0.48)]">
      <button
        type="button"
        aria-expanded={isOpen}
        onClick={onOpen}
        className="flex w-full items-start justify-between gap-4 px-5 py-5 text-left transition hover:bg-[rgba(255,255,255,0.28)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent md:px-6"
      >
        <div>
          <h2 className="font-serif text-2xl text-foreground">{category.title}</h2>
          <p className="mt-2 max-w-2xl text-sm leading-7 text-muted">
            {category.shortDescription}
          </p>
          {isOpen && progressText ? (
            <p className="mt-4 text-[0.72rem] uppercase tracking-[0.2em] text-muted">
              {progressText}
            </p>
          ) : null}
        </div>
        <span className="pt-1 text-xs uppercase tracking-[0.28em] text-muted">
          {isOpen ? "Open" : "View"}
        </span>
      </button>

      {isOpen ? (
        <div className="border-t border-border px-5 py-5 md:px-6">
        <div className="space-y-3">
          {category.questions.slice(0, 5).map((question) => (
            <QuestionChip
              key={question.id}
              title={question.title}
              summary={question.shortLabel}
              href={questionRoute(companySlug, question.id)}
              recommendedNext={question.recommended}
              availabilityStatus={question.availabilityStatus}
            />
          ))}
        </div>
      </div>
      ) : null}
    </section>
  );
}
