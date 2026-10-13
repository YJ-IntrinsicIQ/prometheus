// Approval-guard regression: an answer is served only while its approval record is valid. Read-only against real data;
// fixture registries live in /tmp. There is no rollout flag in this path; approval is the only switch.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { describe, expect, it, vi } from "vitest";

const REAL = path.resolve(process.cwd(), "..", "..");
const realReg = JSON.parse(fs.readFileSync(path.join(REAL, "governance", "approval_registry.json"), "utf8"));
const PAIRS = Object.keys(realReg.approvals);

function fixture(mutate: ((r: any) => void) | "none" | "missing"): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "m522b-"));
  fs.symlinkSync(path.join(REAL, "companies"), path.join(root, "companies"));
  if (mutate !== "missing") {
    fs.mkdirSync(path.join(root, "governance"));
    const reg = JSON.parse(JSON.stringify(realReg));
    if (mutate !== "none") mutate(reg);
    fs.writeFileSync(path.join(root, "governance", "approval_registry.json"), JSON.stringify(reg));
  }
  return root;
}

async function serve(root: string, pair: string) {
  vi.resetModules();
  process.env.ASK_INTRINSICIQ_REPO_ROOT = root;
  const mod = await import("./load-answer-card");
  const [co, q] = pair.split(":");
  return mod.getApprovedHybridCard(co === "sun_pharma" ? "sun-pharma" : co, q);
}

describe("approval guards", () => {
  it("the registry holds the 91 approved pairs (M59.4: 20 original, 6 of them replaced, plus 71 new)", () => {
    expect(PAIRS.length).toBe(91);
  });
  it("S0 real registry: every approved pair is served", async () => {
    for (const p of PAIRS) expect(await serve(REAL, p), p).toBeTruthy();
  }, 120000);
  const negatives: Array<[string, any, string]> = [
    ["S1_registry_missing", "missing", "sun_pharma:how-good-is-management"],
    ["S2_pair_unregistered", (r: any) => { delete r.approvals["sun_pharma:how-good-is-management"]; }, "sun_pharma:how-good-is-management"],
    ["S3_pending_independent", (r: any) => { r.approvals["sun_pharma:how-good-is-management"].status = "PENDING_INDEPENDENT_REVIEW"; }, "sun_pharma:how-good-is-management"],
    ["S4_pending_migration", (r: any) => { r.approvals["sun_pharma:how-good-is-management"].status = "PENDING_MIGRATION_REVIEW"; }, "sun_pharma:how-good-is-management"],
    ["S5_revoked", (r: any) => { r.approvals["sun_pharma:how-good-is-management"].status = "REVOKED"; }, "sun_pharma:how-good-is-management"],
    ["S6_full_digest_mismatch", (r: any) => { r.approvals["sun_pharma:how-good-is-management"].full_artifact_digest = "0".repeat(64); }, "sun_pharma:how-good-is-management"],
    ["S7_fingerprint_mismatch", (r: any) => { r.approvals["sun_pharma:how-good-is-management"].fingerprint = "0".repeat(16); }, "sun_pharma:how-good-is-management"],
    ["S8_unchanged_control", "none", "sun_pharma:how-good-is-management"],
  ];
  for (const [name, mut, pair] of negatives) {
    it(name, async () => {
      const r = await serve(fixture(mut), pair);
      if (name === "S8_unchanged_control") expect(r).toBeTruthy();
      else expect(r).toBeNull(); // fail closed
    }, 60000);
  }
  it("served card content is the approved, identifier-free answer", async () => {
    const r = await serve(REAL, "sun_pharma:how-good-is-management");
    expect(r?.simpleAnswer).toMatch(/^Available records do not establish complete follow-through/); // M54.13 corrected answer (identifier-free)
  }, 60000);
});
