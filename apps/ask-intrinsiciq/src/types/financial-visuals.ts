import type { EvidenceStatus } from "@/src/types/evidence";

export type FinancialVisualType =
  | "line"
  | "bar"
  | "bridge"
  | "comparison"
  | "timeline"
  | "ratio"
  | "status";

export type FinancialVisualPointStatus =
  | "reported"
  | "derived"
  | "partial"
  | "missing"
  | "unreliable";

export type FinancialVisualPoint = {
  period: string;
  value: number | null;
  displayValue: string;
  semanticLabel?: string | null;
  status: FinancialVisualPointStatus;
};

export type FinancialVisualSeries = {
  label: string;
  points: FinancialVisualPoint[];
};

export type FinancialVisualSummary = {
  id: string;
  title: string;
  subtitle: string;
  visualType: FinancialVisualType;
  unit: string;
  series: FinancialVisualSeries[];
  interpretation: string;
  precisionNote?: string | null;
  evidenceStatus: EvidenceStatus;
};
