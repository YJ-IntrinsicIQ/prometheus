import type {
  AskConfidenceLevel,
  AskConvictionImpact,
  AskDiagnostics,
  AskEvidenceItem,
  AskSourceReference,
} from "@/src/lib/prometheus/ask-v2/answer-contracts";

export type ResearchCategoryId =
  | "understand-the-business"
  | "financials"
  | "management"
  | "investor-panel"
  | "risks-and-diligence";

export type ResearchQuestionState = "prepared" | "placeholder";
export type ResearchAnswerStatus =
  | "sourced"
  | "partially_sourced"
  | "not_supported"
  | "placeholder";

export type EvidenceSummary = {
  label: string;
  detail: string;
};

export type UncertaintyNote = {
  label: string;
  detail: string;
};

export type NextQuestion = {
  questionId: string;
  title: string;
};

export type SupportingPoint = {
  title: string;
  detail: string;
};

export type ResearchQuestion = {
  questionId: string;
  title: string;
  summary: string;
  state: ResearchQuestionState;
  recommendedNext?: boolean;
};

export type ResearchCategory = {
  id: ResearchCategoryId;
  name: string;
  description: string;
  questions: ResearchQuestion[];
};

export type ResearchAnswer = {
  questionId: string;
  question: string;
  questionTitle?: string;
  categoryId: ResearchCategoryId;
  state: ResearchQuestionState;
  answerStatus: ResearchAnswerStatus;
  directAnswer: string;
  conciseAnswer?: string;
  explanation: string;
  whyItMatters?: string;
  supportingPoints: SupportingPoint[];
  uncertaintyNote: UncertaintyNote;
  supportingEvidence: EvidenceSummary[];
  evidenceSummary?: EvidenceSummary[];
  nextQuestionIds: string[];
  nextQuestions?: NextQuestion[];
  exploreCategoryId: ResearchCategoryId;
  developmentNote?: string | null;
  conclusion?: string;
  whatChanged?: string;
  whyItChanged?: string;
  convictionImpact?: AskConvictionImpact;
  rawNumbers?: string[];
  unresolved?: string[];
  confidence?: AskConfidenceLevel;
  sources?: AskSourceReference[];
  followUpQuestions?: string[];
  evidence?: AskEvidenceItem[];
  askDiagnostics?: AskDiagnostics;
};

export type QuestionProgress = {
  label: string;
  exploredText: string;
};

export type CompanyResearchView = {
  slug: string;
  name: string;
  fiscalYearLabel: string;
  landingLabel: string;
  tagline: string;
  defaultOpenCategoryId: ResearchCategoryId;
  categories: ResearchCategory[];
  answers: ResearchAnswer[];
  progress: Record<ResearchCategoryId, QuestionProgress>;
  developmentNote?: string | null;
};

export type LandingViewModel = {
  brand: string;
  experience: string;
  tagline: string;
  searchLabel: string;
  searchPlaceholder: string;
  helperText: string;
  demoCompanies: Array<{
    slug: string;
    name: string;
  }>;
};
