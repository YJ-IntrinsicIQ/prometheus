import type { BusinessJourney } from "@/src/types/business-journey";
import type {
  EvidenceSummary,
  UncertaintyNote,
} from "@/src/types/evidence";
import type { FinancialVisualSummary } from "@/src/types/financial-visuals";
import type { AnswerStatus, NextQuestion } from "@/src/types/research-question";
import type { ProductServiceGroup } from "@/src/types/products-services";
import type { ProgressionInsight } from "@/src/types/progression";
import type { InvestorInterpretation } from "@/src/types/investor-interpretation";
import type { QuestionPresentationType } from "@/src/types/question-presentation";

export type ResearchAnswerCard = {
  id: string;
  questionId: string;
  title: string;
  simpleAnswer: string;
  whyItMatters?: string | null;
  keyPoints: string[];
  detailedExplanation: string;
  productsAndServices: ProductServiceGroup[];
  businessJourney?: BusinessJourney | null;
  financialVisualRefs: FinancialVisualSummary["id"][];
  customerRoles?: {
    payers: string[];
    integratorsOrPartners: string[];
    endUsers: string[];
    internationalCustomers: string[];
    concentrationNote: string;
    evidenceStatus: "direct" | "derived" | "partial" | "missing" | "unreliable";
  } | null;
  revenueFlow?: {
    modelType: "project_based" | "recurring" | "mixed" | "unclear";
    steps: Array<{
      order: number;
      label: string;
      explanation: string;
    }>;
    billingBasisNote?: string;
    revenueRecognitionNote?: string;
    cashTimingNote?: string;
    workingCapitalNote?: string;
    evidenceStatus: "direct" | "derived" | "partial" | "missing" | "unreliable";
    offeringExamples?: string[];
  } | null;
  structuredSections?: Array<{
    title: string;
    points: string[];
  }>;
  progression?: ProgressionInsight | null;
  interpretation?: InvestorInterpretation | null;
  evidenceSummary: EvidenceSummary[];
  uncertaintyNote: UncertaintyNote;
  nextQuestions: [NextQuestion, NextQuestion, NextQuestion];
  answerStatus: AnswerStatus;
  questionType: QuestionPresentationType;
  generatedAt: string;
};
