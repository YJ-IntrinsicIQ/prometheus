import { describe, expect, it } from "vitest";
import { containsForbiddenUiTerm } from "./sanitizers";

const ALLOWED = ["EMA validation is dated June 2024", "filing date not stated; validation dated June 2024 and June 3, 2025)"];
const BLOCKED = ["validation passed", "Model validation step", "the validation layer", "Validation", "FDA validation", "validation dated June 2024", "validation dated last week", "internal data pipeline", "see evidence_ids", "stored in companies/sun_pharma/x", "the JSON file", "LLM output"];

describe("sanitizer: determinism and 'validation' exemptions", () => {
  it("allows only the two authorized regulatory phrasings", () => {
    for (const s of ALLOWED) expect(containsForbiddenUiTerm(s), s).toBe(false);
  });
  it.each(BLOCKED)("blocks: %s", (s) => expect(containsForbiddenUiTerm(s)).toBe(true));
  it("is stateless: repeating the same input gives the same answer every time", () => {
    for (const s of [...ALLOWED, ...BLOCKED]) {
      const first = containsForbiddenUiTerm(s);
      for (let i = 0; i < 5; i++) expect(containsForbiddenUiTerm(s), s).toBe(first);
    }
  });
  it("is order-independent: alternating allowed and blocked inputs, forwards, backwards and repeated", () => {
    const expected = new Map([...ALLOWED.map((s) => [s, false] as const), ...BLOCKED.map((s) => [s, true] as const)]);
    const mixed = ALLOWED.flatMap((a, i) => [a, BLOCKED[i], BLOCKED[i + 2]]);
    for (const seq of [mixed, [...mixed].reverse(), [...mixed, ...mixed]]) for (const s of seq) expect(containsForbiddenUiTerm(s), s).toBe(expected.get(s));
  });
});
