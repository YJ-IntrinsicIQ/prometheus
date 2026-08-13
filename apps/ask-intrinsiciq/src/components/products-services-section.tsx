"use client";

import { useMemo, useState } from "react";
import { prepareProductExplanationForDisplay } from "@/src/lib/ask-intrinsiciq/presentation";
import type { ProductServiceGroup } from "@/src/types";

type ProductsServicesSectionProps = {
  groups: ProductServiceGroup[];
};

export function ProductsServicesSection({
  groups,
}: ProductsServicesSectionProps) {
  const visibleGroups = groups.filter((group) => group.items.length > 0);
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});

  const groupedItems = useMemo(
    () =>
      visibleGroups.map((group) => {
        const expanded = expandedGroups[group.id] ?? false;
        const items = expanded ? group.items : group.items.slice(0, 4);
        const hiddenCount = Math.max(group.items.length - 4, 0);

        return { group, items, expanded, hiddenCount };
      }),
    [expandedGroups, visibleGroups],
  );

  if (groupedItems.length === 0) {
    return null;
  }

  return (
    <section className="rounded-[26px] border border-border bg-[rgba(255,255,255,0.44)] p-5 shadow-[0_14px_34px_rgba(15,23,42,0.04)] md:p-6">
      <div data-testid="wide-section-products-services" />
      <div>
        <p className="text-[0.7rem] uppercase tracking-[0.1em] text-muted">
          Products and services
        </p>
        <h2 className="mt-1 text-[1.3rem] font-semibold tracking-[-0.01em] text-foreground md:text-[1.45rem]">
          What the business delivers
        </h2>
      </div>

      <div className="mt-5 space-y-5">
        {groupedItems.map(({ group, items, expanded, hiddenCount }) => (
          <div key={group.id}>
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h3 className="text-[1rem] font-semibold text-foreground">
                  {group.title}
                </h3>
                <p className="mt-1 text-[0.92rem] leading-6 text-muted">
                  {group.description}
                </p>
              </div>
            </div>

            <div className="mt-3 grid gap-3 lg:grid-cols-2">
              {items.map((item) => (
                <article
                  key={item.id}
                  className="rounded-[20px] border border-border bg-[rgba(255,255,255,0.88)] px-4 py-4 shadow-[0_10px_24px_rgba(15,23,42,0.04)]"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-[1rem] font-semibold text-foreground">
                        {item.name}
                      </p>
                      <p className="mt-1 text-[0.9rem] leading-6 text-muted">
                        {prepareProductExplanationForDisplay(item.simpleExplanation)}
                      </p>
                    </div>
                    <span className="rounded-full border border-border bg-white/72 px-2.5 py-1 text-[0.72rem] text-muted">
                      {groupBadge(item.group)}
                    </span>
                  </div>

                  <div className="mt-3 flex flex-wrap gap-2">
                    {(item.customerTypes?.length ? item.customerTypes : [item.customerType])
                      .filter(Boolean)
                      .slice(0, 3)
                      .map((customer) => (
                        <span
                          key={`${item.id}-${customer}`}
                          className="rounded-full border border-border bg-white/78 px-2.5 py-1 text-[0.75rem] text-muted"
                        >
                          {customer}
                        </span>
                      ))}
                  </div>

                  <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-[0.8rem] text-muted">
                    <span>{item.roleInBusiness}</span>
                    <span className="h-1 w-1 rounded-full bg-border" />
                    <span className="inline-flex items-center rounded-full border border-border px-2 py-0.5">
                      {evidenceLabel(item.evidenceStatus)}
                    </span>
                  </div>
                </article>
              ))}
            </div>

            {hiddenCount > 0 ? (
              <button
                type="button"
                onClick={() =>
                  setExpandedGroups((current) => ({
                    ...current,
                    [group.id]: !expanded,
                  }))
                }
                className="mt-3 text-sm text-muted underline decoration-border underline-offset-4 transition hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                {expanded ? "Show fewer" : `Show more (${hiddenCount})`}
              </button>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  );
}

function evidenceLabel(status: ProductServiceGroup["items"][number]["evidenceStatus"]) {
  switch (status) {
    case "direct":
      return "Direct support";
    case "partial":
      return "Partial support";
    case "derived":
      return "Derived evidence";
    case "unreliable":
      return "Low confidence";
    default:
      return "Limited evidence";
  }
}

function groupBadge(group?: string) {
  switch (group) {
    case "product":
      return "Product";
    case "system":
      return "System";
    case "subsystem":
      return "Subsystem";
    case "capability":
      return "Capability";
    case "service":
      return "Service";
    default:
      return "Offering";
  }
}
