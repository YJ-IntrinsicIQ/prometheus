import { notFound } from "next/navigation";
import { AnswerView } from "@/src/components/answer-view";
import { AppFrame } from "@/src/components/layout/app-frame";
import { BrandMark } from "@/src/components/brand-mark";
import {
  getCompanyResearchView,
  getResearchAnswerCard,
  getResearchQuestionParams,
} from "@/src/lib/ask-intrinsiciq";

type QuestionPageProps = {
  params: Promise<{
    companySlug: string;
    questionId: string;
  }>;
};

export const dynamicParams = true;

export async function generateStaticParams() {
  return getResearchQuestionParams();
}

export default async function QuestionPage({ params }: QuestionPageProps) {
  const { companySlug, questionId } = await params;
  const [company, answer] = await Promise.all([
    getCompanyResearchView(companySlug),
    getResearchAnswerCard(companySlug, questionId),
  ]);

  if (!company || !answer) {
    notFound();
  }

  return (
    <AppFrame>
      <section className="editorial-card rounded-[32px] px-6 py-8 md:px-10 md:py-10">
        <BrandMark />
        <div className="mt-12">
          <AnswerView companySlug={companySlug} company={company} answer={answer} />
        </div>
      </section>
    </AppFrame>
  );
}
