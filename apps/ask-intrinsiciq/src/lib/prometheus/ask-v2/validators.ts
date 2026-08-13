import type { ResearchAnswer } from "@/src/types/research";
import type { AskContextV2, AskPlan } from "./answer-contracts";

const FORBIDDEN_INTERNAL_TERMS = [
  "Company Memory",
  "PCIM",
  "CIM",
  "progression engine",
  "artifact",
  "schema",
  "validator",
  "input pack",
  "context builder",
  "LLM",
  "JSON",
  "canonical ID",
  "pipeline stage",
];

export function validateAskPlan(plan: AskPlan) {
  const errors: string[] = [];
  if (!plan.question.trim()) errors.push("question is required");
  if (!plan.primaryIntent) errors.push("primaryIntent is required");
  if (plan.evidenceBudget <= 0) errors.push("evidenceBudget must be positive");
  if (plan.canonicalSourceKeys.length === 0) errors.push("canonicalSourceKeys must not be empty");
  return errors;
}

export function validateAskAnswerV2(answer: ResearchAnswer, context: AskContextV2) {
  const errors: string[] = [];
  if (!answer.directAnswer.trim()) errors.push("directAnswer is required");
  if (!answer.explanation.trim()) errors.push("explanation is required");
  if (!answer.answerStatus) errors.push("answerStatus is required");
  if (context.plan.requiresProgression && !answer.whatChanged?.trim() && !context.progression.length) {
    errors.push("progression question is missing progression evidence");
  }
  if (context.plan.requiresFinancialValues && !answer.rawNumbers?.length && !context.rawNumbers.length) {
    errors.push("financial question is missing raw numbers");
  }
  if (answer.conclusion && hasForbiddenInternalTerm(answer.conclusion)) {
    errors.push("internal terminology leaked in conclusion");
  }
  if (answer.whatChanged && hasForbiddenInternalTerm(answer.whatChanged)) {
    errors.push("internal terminology leaked in whatChanged");
  }
  if (answer.whyItChanged && hasForbiddenInternalTerm(answer.whyItChanged)) {
    errors.push("internal terminology leaked in whyItChanged");
  }
  if (answer.followUpQuestions?.some(hasForbiddenInternalTerm)) {
    errors.push("internal terminology leaked in followUpQuestions");
  }
  return errors;
}

function hasForbiddenInternalTerm(value: string) {
  const lower = value.toLowerCase();
  return FORBIDDEN_INTERNAL_TERMS.some((term) => lower.includes(term.toLowerCase()));
}
