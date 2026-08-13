"use client";

import { useState } from "react";
import Link from "next/link";
import { companyRoute } from "@/src/lib/routes";

type CompanySearchProps = {
  searchLabel: string;
  helperText: string;
  companies: Array<{
    slug: string;
    name: string;
    availabilityState: "READY" | "PARTIAL" | "UNAVAILABLE";
    reportingPeriods: string[];
    primaryIndustry: string;
    summary: string;
  }>;
  showDevelopmentNote?: boolean;
};

export function CompanySearch({
  searchLabel,
  helperText,
  companies,
  showDevelopmentNote = false,
}: CompanySearchProps) {
  const [selectedCompany, setSelectedCompany] = useState(
    companies[0]?.slug ?? "",
  );
  const selectedCompanyData =
    companies.find((company) => company.slug === selectedCompany) ?? companies[0] ?? null;

  return (
    <div className="rounded-[28px] border border-border bg-[rgba(255,255,255,0.5)] p-6">
      <label
        htmlFor="company-select"
        className="text-xs uppercase tracking-[0.28em] text-muted"
      >
        {searchLabel}
      </label>
      <select
        id="company-select"
        value={selectedCompany}
        onChange={(event) => setSelectedCompany(event.target.value)}
        className="mt-4 w-full rounded-[18px] border border-border bg-surface px-4 py-4 text-base text-foreground outline-none"
      >
        {companies.map((company) => (
          <option key={company.slug} value={company.slug}>
            {company.name} · {availabilityLabel(company.availabilityState)}
          </option>
        ))}
      </select>
      <div className="mt-4 space-y-2">
        <p className="text-sm leading-7 text-muted">{helperText}</p>
        {selectedCompanyData ? (
          <div className="rounded-[18px] border border-border bg-[rgba(255,255,255,0.66)] px-4 py-3">
            <p className="text-sm font-medium text-foreground">
              {selectedCompanyData.name}
            </p>
            <p className="mt-1 text-xs uppercase tracking-[0.16em] text-muted">
              {availabilityLabel(selectedCompanyData.availabilityState)}
            </p>
            <p className="mt-2 text-sm leading-6 text-muted">
              {selectedCompanyData.summary}
            </p>
            <p className="mt-2 text-xs leading-6 text-muted">
              {selectedCompanyData.reportingPeriods.join(", ") || "No reporting periods yet"}
              {selectedCompanyData.primaryIndustry
                ? ` • ${selectedCompanyData.primaryIndustry}`
                : ""}
            </p>
          </div>
        ) : null}
      </div>
      {showDevelopmentNote ? (
        <p className="mt-3 text-xs uppercase tracking-[0.18em] text-muted">
          Development fixture
        </p>
      ) : null}
      <Link
        href={companyRoute(selectedCompany)}
        className="mt-8 inline-flex items-center rounded-full bg-accent px-5 py-3 text-sm font-medium text-[var(--surface)] transition hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        Open company questions
      </Link>
    </div>
  );
}

function availabilityLabel(state: CompanySearchProps["companies"][number]["availabilityState"]) {
  switch (state) {
    case "READY":
      return "Ready";
    case "PARTIAL":
      return "Partial";
    case "UNAVAILABLE":
      return "Unavailable";
    default:
      return "Unavailable";
  }
}
