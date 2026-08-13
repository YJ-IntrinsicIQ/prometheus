import type { BusinessJourney } from "@/src/types/business-journey";
import type { ResearchCoverage, SourceState } from "@/src/types/evidence";
import type { FinancialVisualSummary } from "@/src/types/financial-visuals";
import type { ResearchCategory } from "@/src/types/research-question";
import type { ProductServiceGroup } from "@/src/types/products-services";

export type CompanyIdentity = {
  companySlug: string;
  companyName: string;
  displayName: string;
  reportingPeriodsCovered: string[];
  primaryIndustry: string;
  shortDescription: string;
};

export type CompanyResearchView = {
  schemaVersion: string;
  company: CompanyIdentity;
  coverage: ResearchCoverage;
  categories: ResearchCategory[];
  businessJourney?: BusinessJourney | null;
  productsAndServices: ProductServiceGroup[];
  financialVisuals: FinancialVisualSummary[];
  generatedAt: string;
  sourceState: SourceState;
};
