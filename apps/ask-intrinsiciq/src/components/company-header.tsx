import type { CompanyResearchView, SourceState } from "@/src/types";

type CompanyHeaderProps = {
  company: CompanyResearchView;
};

export function CompanyHeader({ company }: CompanyHeaderProps) {
  const periods = company.company.reportingPeriodsCovered.join(", ");
  const summary =
    company.sourceState.uncertaintySummary?.mainUncertainty ?? company.company.shortDescription;
  const contentStatus = company.sourceState.contentStatus ?? "partial";

  return (
    <div>
      <p className="text-xs uppercase tracking-[0.3em] text-muted">Company</p>
      <h1 className="mt-4 font-serif text-5xl leading-tight text-foreground md:text-6xl">
        {company.company.displayName}
      </h1>
      <div className="mt-4 inline-flex rounded-full border border-border bg-[rgba(255,255,255,0.7)] px-3 py-1 text-[0.72rem] uppercase tracking-[0.16em] text-muted">
        {availabilityLabel(contentStatus)}
      </div>
      <p className="mt-6 max-w-xl text-lg leading-8 text-muted">
        {company.coverage.summary}
      </p>
      <p className="mt-4 max-w-xl text-sm leading-6 text-muted">
        {periods}
        {company.company.primaryIndustry
          ? ` • ${company.company.primaryIndustry}`
          : ""}
      </p>
      {summary ? (
        <p className="mt-4 max-w-xl text-sm leading-6 text-muted">
          Important unknown: {summary}
        </p>
      ) : null}
    </div>
  );
}

function availabilityLabel(status: SourceState["contentStatus"]) {
  switch (status) {
    case "supported":
      return "Ready";
    case "partial":
      return "Partial";
    case "unavailable":
      return "Unavailable";
    default:
      return "Partial";
  }
}
