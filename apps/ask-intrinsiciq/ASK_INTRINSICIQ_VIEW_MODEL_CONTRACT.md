# Ask IntrinsicIQ View Model Contract

Canonical frontend data contract for Ask IntrinsicIQ v0.

This document defines the stable UI-facing shape that Prometheus produces for the Ask IntrinsicIQ frontend. The frontend remains a renderer. Prometheus remains the intelligence producer.

This contract is company-agnostic and customer-facing. It must not expose raw Prometheus artifact names, JSON filenames, diagnostics, or pipeline terminology.

## Purpose

- Keep the UI decoupled from Prometheus internal artifact structure.
- Give the frontend one stable, implementation-ready view model.
- Keep the canonical backend output layer and the server-only frontend loader aligned on one stable shape.

## Product principle

One screen. One thought. One next action.

## Top-level entities

1. `CompanyResearchView`
2. `CompanyIdentity`
3. `ResearchCoverage`
4. `ResearchCategory`
5. `ResearchQuestion`
6. `ResearchAnswerCard`
7. `BusinessJourney`
8. `BusinessJourneyStage`
9. `ProductServiceGroup`
10. `ProductServiceItem`
11. `FinancialVisualSummary`
12. `FinancialVisualSeries`
13. `EvidenceSummary`
14. `UncertaintyNote`
15. `NextQuestion`
16. `AnswerStatus`
17. `EvidenceStatus`

## Canonical enums

### AnswerStatus

- `supported`
- `partially_supported`
- `not_supported`
- `unavailable`

### EvidenceStatus

- `direct`
- `derived`
- `partial`
- `missing`
- `unreliable`

## CompanyResearchView

Required shape:

- `schemaVersion`
- `company`
- `coverage`
- `categories`
- `businessJourney`
- `productsAndServices`
- `financialVisuals`
- `generatedAt`
- `sourceState`

Meaning:

- `schemaVersion`: versioned contract string for frontend compatibility.
- `company`: display-safe company identity.
- `coverage`: high-level coverage/readiness summary for the catalog.
- `categories`: curated question catalog.
- `businessJourney`: optional timeline-style explanation of how the business evolved.
- `productsAndServices`: display-safe product and service groupings.
- `financialVisuals`: small-chart-ready financial summaries with UI-safe interpretation.
- `generatedAt`: ISO timestamp for the view-model generation moment.
- `sourceState`: high-level source mode and freshness metadata.

## CompanyIdentity

Required fields:

- `companySlug`
- `companyName`
- `displayName`
- `reportingPeriodsCovered`
- `primaryIndustry`
- `shortDescription`

Rules:

- Must be company-agnostic at the type level.
- `displayName` is the preferred UI label.
- `reportingPeriodsCovered` is an ordered array of display-ready period labels.

## ResearchCoverage

Required fields:

- `availableCategoryIds`
- `sourcedAnswerCount`
- `partiallySupportedAnswerCount`
- `unsupportedAnswerCount`
- `unavailableAnswerCount`
- `evidenceStatus`
- `summary`

Purpose:

- Allows the frontend to understand how complete the research set is without inspecting raw backend artifacts.

## ResearchCategory

Required fields:

- `id`
- `title`
- `shortDescription`
- `displayOrder`
- `questions`

Rules:

- `displayOrder` defines UI ordering.
- `questions` is the curated list rendered by the navigator.

## ResearchQuestion

Required fields:

- `id`
- `categoryId`
- `title`
- `shortLabel`
- `recommended`
- `availabilityStatus`
- `answerCardId`

Rules:

- `id` must be stable and route-safe.
- `recommended` is for subtle UI emphasis only.
- `availabilityStatus` uses the same support semantics as answer cards, but at question-list level.
- `answerCardId` points to the canonical answer payload for that question.

## ResearchAnswerCard

Required fields:

- `id`
- `questionId`
- `title`
- `simpleAnswer`
- `whyItMatters`
- `keyPoints`
- `detailedExplanation`
- `productsAndServices`
- `businessJourney`
- `financialVisualRefs`
- `customerRoles`
- `revenueFlow`
- `structuredSections`
- `interpretation`
- `evidenceSummary`
- `uncertaintyNote`
- `nextQuestions`
- `answerStatus`
- `generatedAt`

Rules:

- `simpleAnswer`: short, beginner-readable, user-facing.
- `whyItMatters`: optional in content quality, but recommended by contract.
- `keyPoints`: maximum 4.
- `detailedExplanation`: longer explanation; the UI may collapse it by default.
- `nextQuestions`: exactly 3.
- `evidenceSummary`: simplified user-facing evidence only.
- `uncertaintyNote`: compact and investor-readable.
- `customerRoles`: optional typed customer-role separation object for customer questions. It must preserve uncertainty when payer / partner / end-user separation is not clearly supported.
- `revenueFlow`: optional compact monetization-flow object for revenue-model answers. It should explain the order-to-cash sequence in a short UI-ready structure rather than repeating the same flow in prose.
- `structuredSections`: optional titled sections for doctrine-style answers such as Buffett. Each section should stay concise and evidence-safe.
- `interpretation`: optional investor-facing summary block with a bottom line, progression, economic mechanism, thesis impact, unresolved items, watch items, and confidence. The frontend should render this block as-is and not rebuild the reasoning client-side.
- No raw internal Prometheus terminology.
- `productsAndServices` and `businessJourney` may be empty/`null` when not relevant, but the type surface must support them.
- Context sections are opt-in per answer. If an answer does not include `businessJourney`, `productsAndServices`, or referenced visuals, the frontend must not inject company-level fallback context on its own.
- `financialVisualRefs` references `FinancialVisualSummary.id` values already present on the same `CompanyResearchView`.
- Public answers must pass a final reconciled-truth cleanup before write so stale “missing CFO/capex/FCF/owner earnings” wording cannot survive when the governed financial truth already exposes those values.
- Public answers should avoid avoidable repetition across `simpleAnswer`, `keyPoints`, `evidenceSummary`, and `uncertaintyNote`.
- Uncertainty-note selection should be ranked per question rather than purely by global severity when the mapped evidence supports more specific uncertainty routing.

## BusinessJourney

Required fields:

- `summary`
- `stages`
- `historicalStages`
- `currentState`
- `statedDirection`
- `currentDirection`
- `openQuestions`

Purpose:

- Gives the frontend a compact, narrative-ready explanation of how the business has evolved over time.
- Public journey generation should separate achieved historical phases, the best-supported current state, and management-stated future direction when evidence supports that distinction.
- Historical phases should reflect real business evolution rather than one phase per fiscal year.

## BusinessJourneyStage

Required fields:

- `id`
- `periodLabel`
- `title`
- `simpleDescription`
- `significance`
- `evidenceStatus`
- `displayOrder`

Rules:

- `periodLabel` is display-ready.
- `significance` explains why the stage matters in plain language.
- `evidenceStatus` tells the UI how strongly the stage is supported.

## BusinessJourneyCurrentState

Required fields:

- `id`
- `periodLabel`
- `title`
- `description`
- `whyItMatters`
- `evidenceStatus`

Rules:

- Represents the best-supported present-tense business state, not a future ambition.

## BusinessJourneyDirection

Required fields:

- `title`
- `description`
- `evidenceStatus`

Rules:

- Must be phrased as stated direction or visible current intent, not as an achieved fact.

## ProductServiceGroup

Required fields:

- `id`
- `title`
- `description`
- `items`

Purpose:

- Lets the UI explain what the company sells or delivers without depending on internal Prometheus grouping names.

## ProductServiceItem

Required fields:

- `id`
- `name`
- `group`
- `simpleExplanation`
- `customerType`
- `customerTypes`
- `roleInBusiness`
- `revenueModel`
- `revenueContributionStatus`
- `revenueContribution`
- `evidenceStatus`
- `sourcePeriods`
- `displayOrder`

Rules:

- Exact revenue contribution is not required.
- `group` must be one of `product`, `system`, `subsystem`, `service`, or `capability`.
- `customerTypes` preserves the compact list form even when `customerType` remains available for older UI readers.
- `revenueModel` should describe the public commercial pattern in plain language without inventing product-level economics.
- `sourcePeriods` should list the public reporting periods that visibly support the item.
- `revenueContributionStatus` should describe whether contribution is known, partially known, or not disclosed.
- `revenueContribution` may be `null` when contribution is unknown or not applicable.
- `displayOrder` defines stable UI ordering inside a product/service group.
- Public output should not exceed 8 offering items plus 4 capability items, and should not render empty groups.

## FinancialVisualSummary

Required fields:

- `id`
- `title`
- `subtitle`
- `visualType`
- `unit`
- `series`
- `interpretation`
- `precisionNote`
- `evidenceStatus`

Supported visual types:

- `line`
- `bar`
- `bridge`
- `comparison`
- `timeline`
- `ratio`
- `status`

Purpose:

- Gives the frontend enough structure to render compact visuals later without knowing Prometheus internals.

## FinancialVisualSeries

Required fields:

- `label`
- `points`

Each point must support:

- `period`
- `value`
- `displayValue`
- `status`

Optional point field:

- `semanticLabel`

Rules:

- `semanticLabel` is recommended for bridge-style or same-period visuals where period/value alone would be ambiguous.

Point status semantics:

- `reported`
- `derived`
- `partial`
- `missing`
- `unreliable`

## EvidenceSummary

Required fields:

- `label`
- `detail`
- `evidenceStatus`

Rules:

- Must be written for an investor-readable frontend, not for internal diagnostics.

## CustomerRoles

Required fields:

- `payers`
- `integratorsOrPartners`
- `endUsers`
- `internationalCustomers`
- `concentrationNote`
- `evidenceStatus`

Rules:

- This is the canonical UI-facing customer-role object.
- It must not mechanically copy the same mixed audience list into every field when the evidence does not support that distinction.
- It should preserve uncertainty explicitly when role separation is incomplete.

## RevenueFlow

Required fields:

- `modelType`
- `steps`
- `cashTimingNote`
- `workingCapitalNote`
- `evidenceStatus`

Optional fields:

- `offeringExamples`

Rules:

- `steps` should usually contain 5 to 6 compact steps.
- The object is intended for a compact visual or stacked flow, not a verbose narrative duplicate.
- `offeringExamples`, when present, should stay short and capped to a few display-safe examples.

## StructuredAnswerSection

Required fields:

- `title`
- `points`

Rules:

- Each section should stay compact and render-safe.
- `points` should be short evidence-safe bullets rather than long stitched paragraphs.

## UncertaintyNote

Required fields:

- `label`
- `detail`
- `evidenceStatus`

Rules:

- Must remain compact.
- Must explain limitation without exposing raw backend plumbing.

## NextQuestion

Required fields:

- `id`
- `questionId`
- `title`
- `shortLabel`

Rules:

- Exactly three are required on each `ResearchAnswerCard`.

## SourceState

Required fields:

- `producer`
- `mode`

Recommended fields:

- `contentStatus`
- `sourceMode`
- `summary`
- `foundSourceCount`
- `missingSourceCount`
- `sourceUpdatedAt`
- `notes`
- `uncertaintySummary`

Recommended `uncertaintySummary` fields:

- `importantUnknownsCount`
- `highSeverityCount`
- `mainUncertainty`
- `unresolvedQuestionCount`

Purpose:

- Lets the frontend know whether it is rendering canonical backend output or a development-only fallback.

## Mapping rules

- The frontend must consume only this view model, not raw company-memory artifacts.
- Backend producers may derive this contract from business intelligence, financial truth, investor-financial modules, and investor-panel outputs, but those raw producer surfaces are not part of the frontend contract.
- Unsupported questions should use `answerStatus = not_supported`.
- Questions that are not yet prepared for the current environment should use `answerStatus = unavailable`.
- The current v0 UI must read canonical Ask IntrinsicIQ output through a server-only loader boundary and must not construct customer-facing investment answers directly inside frontend components.
- The current v0 UI must respect answer-level context routing from the canonical loader and render only the context explicitly attached to that answer.
- Reconciled financial truth has higher precedence than stale investor-lens or committee missing-data wording when the public answer card is finalized.

## Versioning rule

- Breaking changes require a `schemaVersion` change.
- Additive fields may be introduced without breaking existing consumers only if they do not change the meaning of required fields.
