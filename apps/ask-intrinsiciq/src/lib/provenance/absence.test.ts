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
    expect(Object.keys(out)).not.toContain("g5_absence");                 // reachable for audit, never enumerated into a customer payload
    expect(JSON.stringify(out)).not.toContain("g5_absence");
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

import { enforceEvidenceSafety, INTERNAL_KEY } from "./absence";

describe("enforceEvidenceSafety (the one customer rule)", () => {
  const unsafe = entry({ claim: "Market size is not extracted into the records", sentence: "Market size is not extracted into the records, so the runway cannot be assessed.", verification: "UNRESOLVED", state: null, replacement: "Not yet concluded: whether market size is disclosed, which matters because runway depends on it; the industry section would help" });
  it("replaces an unverified definitive sentence, wherever it is nested, and leaves the rest alone", () => {
    const s = { a: ["Revenue grew 10%.", "Market size is not extracted into the records, so the runway cannot be assessed."], b: { c: "keep me" } };
    const out = enforceEvidenceSafety(s, [unsafe]);
    expect(out.a[1]).toMatch(/^Not yet concluded/);
    expect(out.a[0]).toBe("Revenue grew 10%.");
    expect(out.b.c).toBe("keep me");
  });
  it("is idempotent and never touches a VERIFIED entry or a confirmed record statement", () => {
    const once = enforceEvidenceSafety({ t: unsafe.sentence }, [unsafe]);
    expect(enforceEvidenceSafety(once, [unsafe])).toEqual(once);
    const ok = { ...unsafe, record_statement_ok: true };
    expect(enforceEvidenceSafety({ t: unsafe.sentence }, [ok])).toEqual({ t: unsafe.sentence });
    const verified = { ...unsafe, verification: "VERIFIED" as const };
    expect(enforceEvidenceSafety({ t: unsafe.sentence }, [verified])).toEqual({ t: unsafe.sentence });
  });
  it("recognises internal verification keys", () => {
    for (const k of ["g5_absence", "g5_review_pending", "g4_coverage", "g41_progress", "g5_system_statements"]) expect(INTERNAL_KEY.test(k)).toBe(true);
    for (const k of ["simple_answer", "evidence_gaps", "key_points"]) expect(INTERNAL_KEY.test(k)).toBe(false);
  });
});

describe("verified claims carry their verified source figure once", () => {
  const v = entry({ claim: "Return on capital employed is not extracted into the records", verification: "VERIFIED", supplement: "the FY26 report states return on capital employed of 24.2% (consolidated, p.70)" });
  it("appends the supplement and is idempotent", () => {
    const once = enforceEvidenceSafety({ t: "Return on capital employed is not extracted into the records, so returns cannot be assessed." }, [v]);
    expect(once.t).toContain("not extracted into the records; the FY26 report states return on capital employed of 24.2%");
    expect(enforceEvidenceSafety(once, [v])).toEqual(once);
  });
});
