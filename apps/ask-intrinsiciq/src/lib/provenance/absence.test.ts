// M63/G5: the provenance layer only adds a claim-linked ledger; it never changes the rendered content and never invents a state.
import { describe, expect, it } from "vitest";
import { withAbsence, type AbsenceEntry } from "./absence";

const entry = (over: Partial<AbsenceEntry>): AbsenceEntry => ({ claim: "Interest coverage is not extracted into the records", topic: "interest_coverage", state: "NOT_EXTRACTED", verification: "VERIFIED", basis: "the filing carries it", locator: "p.36", evidence_group: "g", ...over });

describe("withAbsence", () => {
  const surface = { name: "panel", uncertain: [{ kind: "Missing measurement", text: "Interest coverage is not extracted into the records, so the burden of debt cannot be tested." }], rows: [["Site-level revenue", "Not in the extracted records"]] };

  it("returns the very same object when there is no ledger", () => {
    expect(withAbsence(surface, [])).toBe(surface);
  });
  it("attaches only the entries whose claim is rendered on the surface, and changes nothing else", () => {
    const out = withAbsence(surface, [entry({}), entry({ claim: "Book value per share is not extracted into the records", topic: "book_value" })]);
    expect(out.g5_absence).toHaveLength(1);
    expect(out.g5_absence![0].topic).toBe("interest_coverage");
    const { g5_absence: _g, ...rest } = out;
    expect(rest).toEqual(surface);
  });
  it("matches a labelled table row through its anchor, not through the shared label text", () => {
    const row = entry({ claim: "Site-level revenue: Not in the extracted records", anchor: "Site-level revenue", topic: "project_outcomes" });
    const other = entry({ claim: "Amount: Not in the extracted records", anchor: "Amount", topic: "transaction_amounts" });
    const out = withAbsence(surface, [row, other]);
    expect(out.g5_absence!.map((e) => e.topic)).toEqual(["project_outcomes"]);
  });
  it("carries an unresolved claim as unresolved, with no state", () => {
    const out = withAbsence(surface, [entry({ state: null, verification: "UNRESOLVED", review: "RQ-x" })]);
    expect(out.g5_absence![0].state).toBeNull();
  });
});
