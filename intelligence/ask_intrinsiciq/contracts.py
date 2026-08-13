from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, TypedDict


ASK_INTRINSICIQ_SCHEMA_VERSION = "ask_intrinsiciq.company_research_view.v1"
ASK_INTRINSICIQ_GENERATOR_VERSION = "0.1.0"

AnswerStatus = Literal[
    "supported",
    "partially_supported",
    "not_supported",
    "unavailable",
]

EvidenceStatus = Literal[
    "direct",
    "derived",
    "partial",
    "missing",
    "unreliable",
]


class CompanyIdentity(TypedDict):
    companySlug: str
    companyName: str
    displayName: str
    reportingPeriodsCovered: List[str]
    primaryIndustry: str
    shortDescription: str


class ResearchCoverage(TypedDict):
    availableCategoryIds: List[str]
    sourcedAnswerCount: int
    partiallySupportedAnswerCount: int
    unsupportedAnswerCount: int
    unavailableAnswerCount: int
    evidenceStatus: EvidenceStatus
    summary: str


class ResearchQuestion(TypedDict):
    id: str
    categoryId: str
    title: str
    shortLabel: str
    recommended: bool
    availabilityStatus: AnswerStatus
    answerCardId: str


class ResearchCategory(TypedDict):
    id: str
    title: str
    shortDescription: str
    displayOrder: int
    questions: List[ResearchQuestion]


class EvidenceSummary(TypedDict):
    status: EvidenceStatus
    summary: str
    supportingItems: List[str]


class UncertaintyNote(TypedDict):
    summary: str


class NextQuestion(TypedDict):
    questionId: str
    title: str
    categoryTitle: str


class ResearchAnswerCard(TypedDict):
    id: str
    questionId: str
    title: str
    simpleAnswer: str
    whyItMatters: str
    keyPoints: List[str]
    detailedExplanation: str
    productsAndServices: List[str]
    businessJourney: Optional[str]
    financialVisualRefs: List[str]
    evidenceSummary: EvidenceSummary
    uncertaintyNote: UncertaintyNote
    nextQuestions: List[NextQuestion]
    answerStatus: AnswerStatus
    generatedAt: str


class BusinessJourneyStage(TypedDict):
    id: str
    periodLabel: str
    title: str
    simpleDescription: str
    significance: str
    evidenceStatus: EvidenceStatus
    displayOrder: int


class BusinessJourney(TypedDict):
    summary: str
    stages: List[BusinessJourneyStage]
    currentDirection: str
    openQuestions: List[str]


class ProductServiceItem(TypedDict):
    id: str
    name: str
    group: str
    simpleExplanation: str
    customerType: str
    customerTypes: List[str]
    roleInBusiness: str
    revenueModel: str
    revenueContributionStatus: str
    revenueContribution: Optional[str]
    evidenceStatus: EvidenceStatus
    sourcePeriods: List[str]
    displayOrder: int


class ProductServiceGroup(TypedDict):
    id: str
    title: str
    description: str
    items: List[ProductServiceItem]


class FinancialVisualSeries(TypedDict):
    label: str
    points: List[Dict[str, Any]]


class FinancialVisualSummary(TypedDict):
    id: str
    title: str
    subtitle: str
    visualType: str
    unit: str
    interpretation: str
    precisionNote: Optional[str]
    evidenceStatus: EvidenceStatus
    series: List[FinancialVisualSeries]


class CompanyResearchView(TypedDict):
    schemaVersion: str
    company: CompanyIdentity
    coverage: ResearchCoverage
    categories: List[ResearchCategory]
    businessJourney: BusinessJourney
    productsAndServices: List[ProductServiceGroup]
    financialVisuals: List[FinancialVisualSummary]
    generatedAt: str
    sourceState: Dict[str, Any]


def empty_business_journey() -> BusinessJourney:
    return {
        "summary": "A business journey view is not yet available in this release.",
        "stages": [],
        "currentDirection": "Not yet prepared.",
        "openQuestions": [],
    }
