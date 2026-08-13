import Link from "next/link";

type QuestionChipProps = {
  title: string;
  summary: string;
  href: string;
  recommendedNext?: boolean;
  availabilityStatus?: "supported" | "partially_supported" | "not_supported" | "unavailable";
};

export function QuestionChip({
  title,
  summary,
  href,
  recommendedNext,
  availabilityStatus = "supported",
}: QuestionChipProps) {
  const content = (
    <div className="flex items-start justify-between gap-4">
      <div>
        <p className="text-base font-medium text-foreground">{title}</p>
        <p className="mt-2 max-w-2xl text-sm leading-7 text-muted">{summary}</p>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-2">
        {recommendedNext ? (
          <span className="rounded-full bg-accent-soft px-3 py-1 text-[0.7rem] font-medium uppercase tracking-[0.18em] text-accent">
            Recommended next
          </span>
        ) : null}
        {availabilityStatus === "unavailable" ? (
          <span className="rounded-full border border-border px-3 py-1 text-[0.68rem] uppercase tracking-[0.16em] text-muted">
            Unavailable
          </span>
        ) : null}
      </div>
    </div>
  );

  return (
    <Link
      href={href}
      className="block rounded-[20px] border border-border bg-surface px-4 py-4 transition hover:border-accent hover:shadow-[0_10px_24px_rgba(20,33,61,0.05)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
    >
      {content}
    </Link>
  );
}
