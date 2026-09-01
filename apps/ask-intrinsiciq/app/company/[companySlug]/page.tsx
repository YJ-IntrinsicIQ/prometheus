import { notFound } from "next/navigation";
import {
  CompanyChangeHighlights,
  buildCompanyChangeHighlights,
} from "@/src/components/company-change-highlights";
import { CompanyHeader } from "@/src/components/company-header";
import { QuestionNavigator } from "@/src/components/question-navigator";
import { AppFrame } from "@/src/components/layout/app-frame";
import { BrandMark } from "@/src/components/brand-mark";
import {
  getCompanyResearchView,
  getResearchAnswerCard,
  getCompanySlugs,
} from "@/src/lib/ask-intrinsiciq";

type CompanyPageProps = {
  params: Promise<{
    companySlug: string;
  }>;
};

export const dynamicParams = true;

export async function generateStaticParams() {
  return (await getCompanySlugs()).map((companySlug) => ({ companySlug }));
}

export default async function CompanyPage({ params }: CompanyPageProps) {
  const { companySlug } = await params;
  const [company, execution, capitalAllocation, risk] = await Promise.all([
    getCompanyResearchView(companySlug),
    getResearchAnswerCard(companySlug, "did-past-claims-come-true"),
    getResearchAnswerCard(companySlug, "how-is-capital-allocated"),
    getResearchAnswerCard(companySlug, "what-can-break-the-thesis"),
  ]);

  if (!company) {
    notFound();
  }

  const highlights = buildCompanyChangeHighlights([
    {
      questionId: "did-past-claims-come-true",
      title: "Did past claims come true?",
      label: "Execution",
      answer: execution,
    },
    {
      questionId: "how-is-capital-allocated",
      title: "How is capital allocated?",
      label: "Economics",
      answer: capitalAllocation,
    },
    {
      questionId: "what-can-break-the-thesis",
      title: "What can break the thesis?",
      label: "Risk",
      answer: risk,
    },
  ]);

  return (
    <AppFrame>
      <section className="editorial-card rounded-[32px] px-6 py-8 md:px-10 md:py-10">
        <BrandMark />
        <div className="mt-12 space-y-8">
          {highlights.length > 0 ? (
            <CompanyChangeHighlights companySlug={companySlug} highlights={highlights} />
          ) : (
            <div className="rounded-[28px] border border-[rgba(74,109,94,0.16)] bg-[rgba(255,255,255,0.72)] px-5 py-5">
              <p className="text-[0.72rem] uppercase tracking-[0.12em] text-muted">
                How the business is changing
              </p>
              <h2 className="mt-2 text-[1.15rem] font-medium text-foreground">
                Research is still incomplete for this company
              </h2>
              <p className="mt-2 max-w-3xl text-sm leading-7 text-muted">
                The route is working, but the company only has partial or unavailable question coverage yet.
                Use the company switcher to compare available evidence across other companies without crossing data between them.
              </p>
            </div>
          )}
          <div className="grid gap-8 lg:grid-cols-[0.76fr_1.24fr] lg:gap-10">
            <CompanyHeader company={company} />
            <QuestionNavigator company={company} />
          </div>
        </div>
      </section>
    </AppFrame>
  );
}
