import Link from "next/link";
import { companyRoute, questionRoute } from "@/src/lib/routes";
import { COMPANIES } from "@/src/lib/story/companies";
import { QUESTIONS } from "@/src/lib/story/question-view";

export function CompanyNav({ active, questionId, panel }: { active: string; questionId?: string; panel?: boolean }) {
  return (
    <nav aria-label="Companies" className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.82rem] text-muted">
      <span>Company:</span>
      {Object.entries(COMPANIES).map(([slug, c]) => (
        <Link key={slug} href={questionId ? questionRoute(slug, questionId) : panel ? `${companyRoute(slug)}/panel` : companyRoute(slug)} aria-current={slug === active ? "page" : undefined} className={slug === active ? "font-medium text-accent" : "hover:text-accent"}>
          {c.name}
        </Link>
      ))}
    </nav>
  );
}

// Every question is listed; one without an approved answer for this company is shown as not available, never hidden or substituted.
export function QuestionNav({ slug, available, active, className = "" }: { slug: string; available: string[]; active?: string; className?: string }) {
  return (
    <nav aria-label="Investor questions" className={className}>
      <p className="text-[0.72rem] font-semibold uppercase tracking-[0.12em] text-muted">Investor questions</p>
      <ul className="mt-2 flex flex-wrap gap-2 text-[0.82rem]">
        {QUESTIONS.map((q) => (
          <li key={q.id}>
            {available.includes(q.id) ? (
              <Link
                href={questionRoute(slug, q.id)}
                aria-current={active === q.id ? "page" : undefined}
                className={`inline-block rounded-full border px-3 py-1.5 ${active === q.id ? "border-accent bg-accent-soft text-accent" : "border-border bg-surface text-muted hover:text-accent"}`}
              >
                {q.family}
              </Link>
            ) : (
              <span title="No approved answer is available yet for this company" className={`inline-block rounded-full border border-dashed border-border px-3 py-1.5 text-muted/70 ${active === q.id ? "bg-surface-strong" : ""}`}>
                {q.family}
              </span>
            )}
          </li>
        ))}
        <li><Link href={`/company/${slug}/questions`} className="inline-block rounded-full border border-dashed border-accent/50 px-3 py-1.5 text-accent hover:bg-accent-soft/50">All questions →</Link></li>
      </ul>
    </nav>
  );
}
