import { render, screen } from "@testing-library/react";
import { FinancialVisualRenderer } from "@/src/components/financial-visual-renderer";
import type { FinancialVisualSummary } from "@/src/types";

describe("FinancialVisualRenderer", () => {
  it("renders semantic labels for bridge points", () => {
    const visuals: FinancialVisualSummary[] = [
      {
        id: "owner_earnings_bridge",
        title: "Owner-oriented cash bridge",
        subtitle: "Current operating cash flow, identified capex, and owner-oriented cash estimate.",
        visualType: "bridge",
        unit: "INR crore",
        interpretation: "Current owner-oriented cash is positive.",
        precisionNote: null,
        evidenceStatus: "derived",
        series: [
          {
            label: "Current bridge",
            points: [
              {
                period: "FY24",
                value: 139.38,
                displayValue: "₹139.38 crore",
                semanticLabel: "Operating cash flow",
                status: "reported",
              },
              {
                period: "FY24",
                value: 41.18,
                displayValue: "₹41.18 crore",
                semanticLabel: "Identified capex",
                status: "derived",
              },
            ],
          },
        ],
      },
    ];

    render(<FinancialVisualRenderer visuals={visuals} />);

    expect(screen.getAllByText(/operating cash flow/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/identified capex/i).length).toBeGreaterThan(0);
  });
});
