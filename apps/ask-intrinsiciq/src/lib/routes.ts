// The only route helpers. The Cockpit is the company page: /company/{slug} (Story, Connections, Discoveries)
// and /company/{slug}/question/{questionId} (investor questions).
export const companyRoute = (companySlug: string) => `/company/${companySlug}`;
export const questionRoute = (companySlug: string, questionId: string) => `/company/${companySlug}/question/${questionId}`;
