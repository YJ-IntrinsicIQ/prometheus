import type {
  BusinessJourney,
  CompanyResearchView,
  FinancialVisualSummary,
  ProductServiceGroup,
  ProductServiceItem,
} from "@/src/types";
import { readJsonIfExists } from "@/src/lib/prometheus/read-json";
import {
  buildCompanyResearchViewFromDiscovery,
  getCompanyDiscoverySummaries,
  getCompanyDiscoverySummary,
  getDiscoveredCompanySlugs,
  resolveInternalKey,
} from "@/src/lib/ask-intrinsiciq/company-discovery";
import { getAskIntrinsicIqPaths, isValidRouteSegment } from "@/src/lib/ask-intrinsiciq/paths";
import { validateCompanyResearchView } from "@/src/lib/ask-intrinsiciq/validate-runtime-view";

type RawCompanyResearchView = {
  schemaVersion: string;
  company: {
    companySlug: string;
    companyName: string;
    displayName: string;
    reportingPeriodsCovered: string[];
    primaryIndustry: string;
    shortDescription: string;
  };
  coverage: CompanyResearchView["coverage"];
  categories: CompanyResearchView["categories"];
  businessJourney?: BusinessJourney | null;
  productsAndServices: ProductServiceGroup[];
  financialVisuals: FinancialVisualSummary[];
  generatedAt: string;
  sourceState: {
    contentStatus?: "supported" | "partial" | "unavailable";
    foundSourceCount?: number;
    missingSourceCount?: number;
    sourceMode?: string;
    summary?: string;
    uncertaintySummary?: CompanyResearchView["sourceState"]["uncertaintySummary"];
  };
};

type RawBusinessJourneyPayload = {
  company_slug?: string;
  summary: string;
  current_direction: string;
  open_questions: string[];
  stages: Array<{
    id: string;
    period_label: string;
    title: string;
    simple_description: string;
    significance: string;
    evidence_status: BusinessJourney["stages"][number]["evidenceStatus"];
    display_order: number;
  }>;
};

type RawProductsServicesPayload = {
  company_slug?: string;
  groups: Array<{
    id: string;
    title: string;
    description: string;
      items: Array<{
        id: string;
        name: string;
        group?: string;
        simple_explanation: string;
        customer_type: string;
        customer_types?: string[];
        role_in_business: string;
        revenue_model?: string;
        revenue_contribution_status: ProductServiceItem["revenueContributionStatus"];
        revenue_contribution: string | null;
        evidence_status: ProductServiceItem["evidenceStatus"];
        source_periods?: string[];
        display_order: number;
      }>;
  }>;
};

type RawFinancialVisualsPayload = {
  company_slug?: string;
  visuals: Array<{
    id: string;
    title: string;
    subtitle: string;
    visual_type: FinancialVisualSummary["visualType"];
    unit: string;
    series: Array<{
      label: string;
      points: Array<{
        period: string;
        value: number | null;
        display_value: string;
        semantic_label?: string | null;
        status: FinancialVisualSummary["series"][number]["points"][number]["status"];
      }>;
    }>;
    interpretation: string;
    precision_note?: string | null;
    evidence_status: FinancialVisualSummary["evidenceStatus"];
  }>;
};

type RawValidationReport = {
  status?: string;
};

type RawManifest = {
  validation_status?: string;
};

function logRuntimeIssue(message: string, detail?: unknown) {
  console.error(`[Ask IntrinsicIQ] ${message}`, detail);
}

function artifactCompanyMatches(
  companySlug: string,
  artifactCompanySlug: string | null | undefined,
  artifactPath: string,
) {
  if (!artifactCompanySlug || artifactCompanySlug === companySlug) {
    return true;
  }

  logRuntimeIssue("Company-scoped artifact rejected because company identity mismatched.", {
    failure_class: "CROSS_COMPANY_INTELLIGENCE_CONTAMINATION",
    requested_company: companySlug,
    artifact_company: artifactCompanySlug,
    artifact_path: artifactPath,
  });
  return false;
}

function mapBusinessJourney(
  value: RawBusinessJourneyPayload | null,
): BusinessJourney | null {
  if (!value) {
    return null;
  }

  return {
    summary: value.summary,
    currentDirection: value.current_direction,
    openQuestions: value.open_questions,
    stages: value.stages
      .slice()
      .sort((left, right) => left.display_order - right.display_order)
      .map((stage) => ({
        id: stage.id,
        periodLabel: stage.period_label,
        title: stage.title,
        simpleDescription: stage.simple_description,
        significance: stage.significance,
        evidenceStatus: stage.evidence_status,
        displayOrder: stage.display_order,
      })),
  };
}

function mapProductsAndServices(
  value: RawProductsServicesPayload | null,
): ProductServiceGroup[] {
  if (!value) {
    return [];
  }

  return value.groups.map((group) => ({
    id: group.id,
    title: group.title,
    description: group.description,
    items: group.items
      .slice()
      .sort((left, right) => left.display_order - right.display_order)
      .map((item) => ({
        id: item.id,
        name: item.name,
        group: item.group,
        simpleExplanation: item.simple_explanation,
        customerType: item.customer_type,
        customerTypes: item.customer_types ?? [],
        roleInBusiness: item.role_in_business,
        revenueModel: item.revenue_model ?? undefined,
        revenueContributionStatus: item.revenue_contribution_status,
        revenueContribution: item.revenue_contribution,
        evidenceStatus: item.evidence_status,
        sourcePeriods: item.source_periods ?? [],
        displayOrder: item.display_order,
      })),
  }));
}

function mapFinancialVisuals(
  value: RawFinancialVisualsPayload | null,
): FinancialVisualSummary[] {
  if (!value) {
    return [];
  }

  return value.visuals.map((visual) => ({
    id: visual.id,
    title: visual.title,
    subtitle: visual.subtitle,
    visualType: visual.visual_type,
    unit: visual.unit,
    series: visual.series.map((series) => ({
      label: series.label,
      points: series.points.map((point) => ({
        period: point.period,
        value: point.value,
        displayValue: point.display_value,
        semanticLabel: point.semantic_label ?? null,
        status: point.status,
      })),
    })),
    interpretation: visual.interpretation,
    precisionNote: visual.precision_note ?? null,
    evidenceStatus: visual.evidence_status,
  }));
}

async function loadCanonicalCompanyResearchView(
  publicSlug: string,
  internalKey: string,
): Promise<CompanyResearchView | null> {
  const paths = getAskIntrinsicIqPaths(internalKey);

  if (!paths) {
    return null;
  }

  const [rawView, rawJourney, rawProducts, rawVisuals, manifest, report] =
    await Promise.all([
      readJsonIfExists<RawCompanyResearchView>(paths.companyResearchView),
      readJsonIfExists<RawBusinessJourneyPayload>(paths.businessJourney),
      readJsonIfExists<RawProductsServicesPayload>(paths.productsServices),
      readJsonIfExists<RawFinancialVisualsPayload>(paths.financialVisualSummaries),
      readJsonIfExists<RawManifest>(paths.manifest),
      readJsonIfExists<RawValidationReport>(paths.validationReport),
    ]);

  if (!rawView) {
    return null;
  }

  if (
    !artifactCompanyMatches(
      internalKey,
      rawView.company?.companySlug,
      paths.companyResearchView,
    )
  ) {
    return null;
  }

  if (
    !artifactCompanyMatches(internalKey, rawJourney?.company_slug, paths.businessJourney) ||
    !artifactCompanyMatches(internalKey, rawProducts?.company_slug, paths.productsServices) ||
    !artifactCompanyMatches(internalKey, rawVisuals?.company_slug, paths.financialVisualSummaries)
  ) {
    return null;
  }

  if (report?.status === "fail" || manifest?.validation_status === "fail") {
    logRuntimeIssue("Canonical Ask IntrinsicIQ validation failed.", {
      companySlug: internalKey,
      report,
      manifest,
    });
    return null;
  }

  const mapped: CompanyResearchView = {
    schemaVersion: rawView.schemaVersion,
    company: {
      ...rawView.company,
      companySlug: publicSlug,
    },
    coverage: rawView.coverage,
    categories: rawView.categories,
    businessJourney: mapBusinessJourney(rawJourney ?? null) ?? rawView.businessJourney ?? null,
    productsAndServices:
      mapProductsAndServices(rawProducts ?? null) ?? rawView.productsAndServices,
    financialVisuals:
      mapFinancialVisuals(rawVisuals ?? null) ?? rawView.financialVisuals,
    generatedAt: rawView.generatedAt,
    sourceState: {
      producer: "prometheus",
      mode: "backend",
      contentStatus: rawView.sourceState?.contentStatus ?? null,
      sourceMode: rawView.sourceState?.sourceMode ?? null,
      summary: rawView.sourceState?.summary ?? null,
      foundSourceCount: rawView.sourceState?.foundSourceCount ?? null,
      missingSourceCount: rawView.sourceState?.missingSourceCount ?? null,
      sourceUpdatedAt: rawView.generatedAt,
      uncertaintySummary: rawView.sourceState?.uncertaintySummary ?? null,
    },
  };

  const errors = validateCompanyResearchView(mapped);

  if (errors.length > 0) {
    logRuntimeIssue("Canonical company research view failed runtime validation.", {
      companySlug: publicSlug,
      errors,
    });
    return null;
  }

  return mapped;
}

export async function getCompanyResearchView(
  publicSlug: string,
): Promise<CompanyResearchView | null> {
  if (!isValidRouteSegment(publicSlug)) {
    return null;
  }

  const internalKey = await resolveInternalKey(publicSlug);
  if (!internalKey) {
    return null;
  }

  const canonical = await loadCanonicalCompanyResearchView(publicSlug, internalKey);

  if (canonical) {
    return canonical;
  }

  const discovery = await getCompanyDiscoverySummary(publicSlug);
  if (discovery) {
    return buildCompanyResearchViewFromDiscovery(discovery.internalKey, discovery.slug, discovery);
  }

  return null;
}

export async function getBusinessJourney(
  companySlug: string,
): Promise<BusinessJourney | null> {
  const company = await getCompanyResearchView(companySlug);
  return company?.businessJourney ?? null;
}

export async function getProductsServices(
  companySlug: string,
): Promise<ProductServiceGroup[] | null> {
  const company = await getCompanyResearchView(companySlug);
  return company?.productsAndServices ?? null;
}

export async function getFinancialVisuals(
  companySlug: string,
): Promise<FinancialVisualSummary[]> {
  const company = await getCompanyResearchView(companySlug);
  return company?.financialVisuals ?? [];
}

export async function getCompanySlugs() {
  return getDiscoveredCompanySlugs();
}

export async function getLandingCompanies() {
  const companies = await getCompanyDiscoverySummaries();
  return companies.map((company) => ({
    slug: company.slug,
    name: company.name,
    availabilityState: company.availabilityState,
    reportingPeriods: company.reportingPeriods,
    primaryIndustry: company.primaryIndustry,
    summary: company.summary,
    importantUnknown: company.importantUnknown,
    questionIds: company.questionIds,
  }));
}
