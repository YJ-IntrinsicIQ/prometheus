// M63/G2: the consumers read the canonical definitions instead of re-deriving them.
import { describe, expect, it } from "vitest";
import { buildAccountability, commitmentDeadline } from "./accountability";
import { completedDeals } from "./capital";
import { parseCommitmentEvidence } from "./commitment-evidence";
import { evidencePeriod } from "./question-view";

type Obj = Record<string, unknown>;

describe("deadline: one interpretation, stamped by the register's classifier", () => {
  it("uses the canonical deadline, including one stated inside the statement", () => {
    const m = { expected_timeframe: "unspecified", commitment_basis: { deadline_text: "by FY 2025-26", deadline_year: 2026, deadline_source: "statement" } };
    expect(commitmentDeadline(m)).toEqual({ text: "by FY 2025-26", year: 2026 });
  });
  it("a register that carries the basis but no deadline means 'no deadline', whatever the old regexes would find", () => {
    expect(commitmentDeadline({ expected_timeframe: "by 2025", commitment_basis: { deadline_text: null, deadline_year: null } })).toBeNull();
  });
  it("an older register without the basis falls back to the legacy reading", () => {
    expect(commitmentDeadline({ expected_timeframe: "By 2030" })).toEqual({ text: "by 2030", year: 2030 });
    expect(commitmentDeadline({ expected_timeframe: "H1CY24" })).toEqual({ text: "H1 2024", year: 2024 });
  });
  it("the Story chain shows the canonical year", () => {
    const register: Obj[] = [{ id: "MC-0043", commitment_fingerprint: "f1", verification_applicability: "APPLICABLE", original_statement: "Establish 9 more RACs by FY 2025-26", announcement_period: "fy25", status: "Unable To Verify", expected_timeframe: "unspecified", commitment_basis: { deadline_text: "by FY 2025-26", deadline_year: 2026 } }];
    expect(buildAccountability({ commitments: register, projects: [] }).chains[0].deadline).toBe("by 2026");
  });
});

describe("a row read from approved-answer text is hard only if the register's classification agrees (by identity, never shipped)", () => {
  const promises: Obj = {
    deterministic_precision_facts: ["Hard commitment 1 — MC-0029 (FY24): Co-process 30% of hazardous waste.; timeframe=By 2025; reported progress=47% (FY25)"],
    what_evidence_shows: ["Hard commitments: (1) hazardous waste 47% in FY25 (p.103);"],
  };
  const row = (register: Obj[]) => parseCommitmentEvidence(promises, null, register)[0];
  it("an older register (no flag) leaves the row as parsed", () => expect(row([{ id: "MC-0029" }]).hard).toBe(true));
  it("a register that says hard keeps it", () => expect(row([{ id: "MC-0029", hard_commitment: true }]).hard).toBe(true));
  it("a register that says NOT hard wins over the frozen text", () => expect(row([{ id: "MC-0029", hard_commitment: false }]).hard).toBe(false));
  it("the register identity does not leak into the row", () => expect(JSON.stringify(row([{ id: "MC-0029", hard_commitment: true }]))).not.toMatch(/MC-\d+/));
});

describe("announced is not completed; an annual amount is not a multi-year total", () => {
  const deal = (state: string): Obj => ({ action_type: "acquisition", deployment_state: state, action_description: "Acquisition (Target Co)", deployment_periods: ["fy25"] });
  it("only a COMPLETED_TRANSACTION is a completed deal", () => {
    expect(completedDeals([deal("COMPLETED_TRANSACTION")])).toHaveLength(1);
    for (const state of ["ANNOUNCED", "ACTION_STARTED", "UNKNOWN", "UNABLE_TO_VERIFY"]) expect(completedDeals([deal(state)])).toHaveLength(0);
  });
  it("a year after the latest annual report is an as-of date or a deadline, not filing evidence", () => {
    const e = evidencePeriod("Revenue grew from FY24 to FY25. The 9 centres are due by FY 2025-26.", ["annual_report_fy24.pdf", "annual_report_fy25.pdf"]);
    expect(e.period).toBe("FY24–FY25");
    expect(e.note).toMatch(/FY26 appears only as an as-of date or a deadline/);
  });
});
