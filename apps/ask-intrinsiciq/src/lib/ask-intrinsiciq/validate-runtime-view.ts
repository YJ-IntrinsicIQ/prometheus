import type { CompanyResearchView, ResearchAnswerCard } from "@/src/types";
import { containsForbiddenUiTerm } from "@/src/lib/prometheus/sanitizers";

function hasForbiddenTerms(value: unknown): boolean {
  if (typeof value === "string") {
    return containsForbiddenUiTerm(value);
  }

  if (Array.isArray(value)) {
    return value.some((entry) => hasForbiddenTerms(entry));
  }

  if (value && typeof value === "object") {
    return Object.values(value).some((entry) => hasForbiddenTerms(entry));
  }

  return false;
}

export function validateCompanyResearchView(
  value: CompanyResearchView,
): string[] {
  const errors: string[] = [];

  if (!value.schemaVersion) {
    errors.push("Missing schemaVersion.");
  }

  if (!value.company?.companySlug) {
    errors.push("Missing company slug.");
  }

  if (!Array.isArray(value.categories) || value.categories.length === 0) {
    errors.push("Missing categories.");
  }

  if (hasForbiddenTerms(value)) {
    errors.push("Customer-facing content contains forbidden internal terms.");
  }

  return errors;
}

export function validateResearchAnswerCard(
  value: ResearchAnswerCard,
): string[] {
  const errors: string[] = [];

  if (!value.questionId) {
    errors.push("Missing questionId.");
  }

  if (!value.title) {
    errors.push("Missing answer title.");
  }

  if (!Array.isArray(value.nextQuestions) || value.nextQuestions.length !== 3) {
    errors.push("Answers must contain exactly three next questions.");
  }

  if (value.keyPoints.length > 4) {
    errors.push("Answers may contain at most four key points.");
  }

  if (hasForbiddenTerms(value)) {
    errors.push("Customer-facing answer content contains forbidden internal terms.");
  }

  return errors;
}
