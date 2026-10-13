// The five questions with certified (approved) answers in the Cockpit. Their ids are the ids of the approved answers.
// A catalog question maps onto one of these through the catalog (see lib/catalog); this list is not a second catalog.
export const QUESTIONS = [
  { id: "what-has-management-promised", family: "Management Promises", title: "What has management promised?" },
  { id: "what-did-management-actually-deliver", family: "Management Delivery", title: "What did management actually deliver?" },
  { id: "what-could-go-wrong", family: "Risks / Diligence", title: "What could go wrong?" },
  { id: "how-is-capital-allocated", family: "Capital Allocation", title: "How is capital allocated?" },
  { id: "how-good-is-management", family: "Management Intelligence", title: "How good is management?" },
] as const;
