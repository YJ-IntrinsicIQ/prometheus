import { describe, expect, it } from "vitest";
import { capexProgramme } from "./capital";

const capex = (extra: Record<string, unknown> = {}) => ({ action_type: "organic_capex", deployment_state: "DEPLOYED", amount_inr_cr: 3609.37, deployment_periods: ["fy20", "fy21", "fy22", "fy26"], ...extra });

describe("capex amount keeps its own period (G1)", () => {
  it("a stamped amount is labelled with its own year, not the deployment span", () => {
    const p = capexProgramme([capex({ amount_period: "fy26" })])!;
    expect(p.span).toBe("FY26");
    expect(p.label).toBe("₹3,609 cr in FY26");
    expect(p.label).not.toMatch(/FY20/);
  });
  it("an older artifact without amount_period renders exactly as before", () => {
    const p = capexProgramme([capex()])!;
    expect(p.span).toBe("FY20–FY26");
    expect(p.label).toBe("₹3,609 cr across FY20–FY26");
  });
  it("an amount with no multi-year record is not a programme", () => {
    expect(capexProgramme([capex({ deployment_periods: ["fy26"] })])).toBeNull();
  });
});
