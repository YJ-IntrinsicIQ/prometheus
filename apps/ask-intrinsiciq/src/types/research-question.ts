export type AnswerStatus =
  | "supported"
  | "partially_supported"
  | "not_supported"
  | "unavailable";

export type ResearchQuestionAvailabilityStatus =
  | "supported"
  | "partially_supported"
  | "not_supported"
  | "unavailable";

export type ResearchQuestion = {
  id: string;
  categoryId: string;
  title: string;
  shortLabel: string;
  recommended: boolean;
  availabilityStatus: ResearchQuestionAvailabilityStatus;
  answerCardId: string;
};

export type ResearchCategory = {
  id: string;
  title: string;
  shortDescription: string;
  displayOrder: number;
  questions: ResearchQuestion[];
};

export type NextQuestion = {
  id: string;
  questionId: string;
  title: string;
  shortLabel: string;
};
