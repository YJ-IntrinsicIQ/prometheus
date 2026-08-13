"use client";

import { useState } from "react";
import type { EvidenceSummary } from "@/src/types";

type EvidenceDisclosureProps = {
  items: EvidenceSummary[];
};

export function EvidenceDisclosure({ items }: EvidenceDisclosureProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-[24px] border border-border bg-[rgba(255,255,255,0.42)] p-5">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center justify-between gap-3 text-left"
      >
        <span className="text-[0.98rem] font-medium text-foreground">
          View supporting evidence
        </span>
        <span className="text-[0.8rem] text-muted">
          {open ? "Hide" : "Show"}
        </span>
      </button>

      {open ? (
        <ul className="mt-4 space-y-3">
          {items.map((item) => (
            <li key={item.label} className="rounded-[18px] bg-surface px-4 py-4">
              <p className="text-[0.95rem] font-medium text-foreground">{item.label}</p>
              <p className="mt-2 text-[0.92rem] leading-7 text-muted">{item.detail}</p>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
