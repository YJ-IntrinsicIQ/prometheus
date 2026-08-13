import type { QuestionPresentationType } from "@/src/types/question-presentation";

const QUESTION_TYPE_BY_ID: Record<string, QuestionPresentationType> = {
  "what-does-company-do": "factual",
  "who-are-the-customers": "factual",
  "how-does-it-make-money": "factual",
  "what-makes-the-offering-important": "factual",
  "where-is-evidence-thin": "diligence",
  "are-profits-converting-into-cash": "financial",
  "what-is-owner-earnings": "financial",
  "is-working-capital-a-concern": "financial",
  "are-per-share-economics-improving": "financial",
  "which-financial-assumption-matters-most": "financial",
  "what-has-management-promised": "progression",
  "did-past-claims-come-true": "progression",
  "what-projects-are-underway": "progression",
  "how-is-capacity-changing": "progression",
  "what-is-management-commentary-saying": "progression",
  "how-is-capital-allocated": "capital_allocation",
  "what-incentives-matter": "management_quality",
  "what-should-i-ask-ir": "diligence",
  "what-would-graham-worry-about": "investor_lens",
  "what-would-buffett-focus-on": "investor_lens",
  "where-would-fisher-be-curious": "investor_lens",
  "what-would-munger-avoid": "investor_lens",
  "how-would-lynch-explain-it": "investor_lens",
  "what-can-break-the-thesis": "risk",
  "which-disclosure-is-missing": "diligence",
  "what-evidence-would-change-the-view": "diligence",
  "what-needs-management-clarification": "diligence",
  "what-remains-unresolved": "diligence",
  "what-are-key-risks": "risk",
};

export function getQuestionPresentationType(questionId: string): QuestionPresentationType {
  return QUESTION_TYPE_BY_ID[questionId] ?? "factual";
}

export function shouldShowInvestorInterpretation(questionType: QuestionPresentationType): boolean {
  return questionType !== "factual";
}
