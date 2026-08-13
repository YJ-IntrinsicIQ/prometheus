export function companyRoute(companySlug: string) {
  return `/company/${companySlug}`;
}

export function questionRoute(companySlug: string, questionId: string) {
  return `/company/${companySlug}/question/${questionId}`;
}

export function backToQuestionsRoute(companySlug: string) {
  return companyRoute(companySlug);
}
