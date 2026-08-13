export type EvidenceStatus =
  | "direct"
  | "derived"
  | "partial"
  | "missing"
  | "unreliable";

export type EvidenceSummary = {
  label: string;
  detail: string;
  evidenceStatus: EvidenceStatus;
};

export type UncertaintyNote = {
  label: string;
  detail: string;
  evidenceStatus: EvidenceStatus;
};

export type ResearchCoverage = {
  availableCategoryIds: string[];
  sourcedAnswerCount: number;
  partiallySupportedAnswerCount: number;
  unsupportedAnswerCount: number;
  unavailableAnswerCount: number;
  evidenceStatus: EvidenceStatus;
  summary: string;
};

export type SourceState = {
  producer: "prometheus";
  mode: "demo" | "backend";
  contentStatus?: "supported" | "partial" | "unavailable" | null;
  sourceMode?: string | null;
  summary?: string | null;
  foundSourceCount?: number | null;
  missingSourceCount?: number | null;
  sourceUpdatedAt?: string | null;
  notes?: string[];
  uncertaintySummary?: {
    importantUnknownsCount: number;
    highSeverityCount: number;
    mainUncertainty: string;
    unresolvedQuestionCount: number;
  } | null;
};
