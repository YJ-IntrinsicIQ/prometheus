import Link from "next/link";
import type { ReactNode } from "react";
import { companyRoute } from "@/src/lib/routes";
import { CompanyNav, QuestionNav } from "./question-nav";
import { EvidenceProvider } from "./evidence";

/** The one frame every Cockpit page uses: way back, company switcher, Story/Connections/Discoveries, the five questions. */
export function CockpitShell({ slug, company, available, docs, titles, activeQuestion, panel, children }: { slug: string; company: string; available: string[]; docs: string[]; titles?: Record<string, string>; activeQuestion?: string; panel?: boolean; children: ReactNode }) {
  return (
    <EvidenceProvider slug={slug} company={company} docs={docs} available={available} titles={titles}>
    <main className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
      <p className="mb-3 text-[0.85rem]">
        <Link href="/" className="text-accent hover:underline">← All companies</Link>
      </p>
      <p className="inline-block rounded-full bg-gold-soft px-3 py-1 text-[0.72rem] font-medium text-[#6f5320]">Investor view · approved intelligence only</p>
      <p className="mt-4 text-[0.85rem] text-muted">
        {company} · <Link href={companyRoute(slug)} className="text-accent hover:underline">The Story</Link> ·{" "}
        <Link href={`${companyRoute(slug)}#connections`} className="text-accent hover:underline">Connections</Link> ·{" "}
        <Link href={`${companyRoute(slug)}#discoveries`} className="text-accent hover:underline">Discoveries</Link> ·{" "}
        <Link href={`${companyRoute(slug)}/questions`} className="text-accent hover:underline">All questions</Link> ·{" "}
        <Link href={`${companyRoute(slug)}/panel`} aria-current={panel ? "page" : undefined} className={panel ? "font-medium text-accent" : "text-accent hover:underline"}>Investment Panel</Link>
      </p>
      <CompanyNav active={slug} questionId={activeQuestion} panel={panel} />
      <QuestionNav slug={slug} available={available} active={activeQuestion} className="mt-4" />
      {children}
    </main>
    </EvidenceProvider>
  );
}

/** Honest empty state: nothing is borrowed from another company or from unapproved analysis. */
export function Unavailable({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-8 rounded-[20px] border border-dashed border-border bg-surface p-5">
      <h2 className="font-serif text-[1.3rem] text-foreground">{title}</h2>
      <div className="mt-2 text-[0.92rem] leading-7 text-muted">{children}</div>
    </section>
  );
}
