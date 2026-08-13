import type { RawSources } from "../answer-builders";
import type { AskContextV2, AskPlan } from "./answer-contracts";
import { buildAskContextV2, buildAskV2Summary } from "./context-builder";
import { buildAskPlan } from "./router";
import { validateAskAnswerV2, validateAskPlan } from "./validators";

export type AskResponseV2 = ReturnType<typeof buildAskV2Summary> & {
  question: string;
  questionId?: string;
  plan: AskPlan;
  context: AskContextV2;
  validationIssues: string[];
};

export function buildAskResponseV2(
  question: string,
  sources: RawSources,
  questionId?: string,
): AskResponseV2 {
  const plan = buildAskPlan(question, questionId);
  const planIssues = validateAskPlan(plan);
  const context = buildAskContextV2(sources, plan);
  const summary = buildAskV2Summary(context);
  const validationIssues = [...planIssues, ...validateAskAnswerV2(toValidationAnswer(summary), context)];

  return {
    question,
    questionId,
    plan,
    context,
    validationIssues,
    ...summary,
    askDiagnostics: {
      ...(summary.askDiagnostics as Record<string, unknown>),
      validationStatus: validationIssues.length === 0 ? "pass" : "warning",
    } as typeof summary.askDiagnostics,
  };
}

function toValidationAnswer(summary: ReturnType<typeof buildAskV2Summary>) {
  return {
    questionId: "",
    question: summary.conclusion || "",
    categoryId: "financials" as const,
    state: "prepared" as const,
    answerStatus: "sourced" as const,
    directAnswer: summary.conclusion || "",
    explanation: summary.whyItMatters || "",
    supportingPoints: [],
    uncertaintyNote: {
      label: "Uncertainty note",
      detail: "",
    },
    supportingEvidence: [],
    nextQuestionIds: [],
    exploreCategoryId: "financials" as const,
  };
}
