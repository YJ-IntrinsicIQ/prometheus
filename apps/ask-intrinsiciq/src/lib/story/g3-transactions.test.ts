// M63/G3: a signed-but-not-completed acquisition is shown as that, with the filing's own terms and status sentence.
import { describe, expect, it } from "vitest";
import { dealName, pendingDeals, completedDeals } from "./capital";
import { investmentEvents } from "./story-events";

type Obj = Record<string, unknown>;
const signed: Obj = {
  action_type: "acquisition", action_description: "Proposed acquisition of Orion (signed; closing pending)", deployment_state: "ANNOUNCED", deployment_periods: ["fy26"], amount_inr_cr: null,
  transaction_status: "signed_pending_completion", transaction_terms: "US$ 14.00 per share in an all cash transaction with an enterprise valuation of US$ 11.75 Billion", transaction_status_basis: "remains subject to shareholder and regulatory approvals",
};
const done: Obj = { action_type: "acquisition", action_description: "Acquisition (Vega Ltd)", deployment_state: "COMPLETED_TRANSACTION", deployment_periods: ["fy25"], amount_inr_cr: 120 };

describe("signed is not completed", () => {
  it("names the target and keeps it out of the completed list", () => {
    expect(dealName(signed)).toBe("Orion");
    expect(pendingDeals([signed, done])).toEqual([signed]);
    expect(completedDeals([signed, done])).toEqual([done]);
  });
  it("the Story event says signed, not completed, with the stated terms and the filing's status sentence", () => {
    const events = investmentEvents([signed, done], null);
    const pending = events.find((e) => e.key.startsWith("pending-deal"))!;
    expect(pending.headline).toBe("Acquisition signed, not completed: Orion");
    expect(pending.summary).toMatch(/US\$ 14\.00 per share/);
    expect(pending.summary).toMatch(/remains subject to shareholder and regulatory approvals/);
    expect(JSON.stringify(pending)).not.toMatch(/acquisition completed|completed acquisition/i);
    expect(events.some((e) => /Acquisition completed: Vega Ltd/.test(e.headline))).toBe(true);
  });
  it("an announced deal with no recorded status is not shown as pending or completed", () => {
    expect(pendingDeals([{ ...signed, transaction_status: undefined }])).toEqual([]);
  });
});
