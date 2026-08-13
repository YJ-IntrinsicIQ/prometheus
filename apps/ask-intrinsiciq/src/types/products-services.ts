import type { EvidenceStatus } from "@/src/types/evidence";

export type RevenueContributionStatus =
  | "known"
  | "partial"
  | "unknown"
  | "not_applicable";

export type ProductServiceItem = {
  id: string;
  name: string;
  group?: string;
  simpleExplanation: string;
  customerType: string;
  customerTypes?: string[];
  roleInBusiness: string;
  revenueModel?: string;
  revenueContributionStatus: RevenueContributionStatus;
  revenueContribution?: string | null;
  evidenceStatus: EvidenceStatus;
  sourcePeriods?: string[];
  displayOrder: number;
};

export type ProductServiceGroup = {
  id: string;
  title: string;
  description: string;
  items: ProductServiceItem[];
};
