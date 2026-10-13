import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { getRepoRoot } from "@/src/lib/ask-intrinsiciq/paths";
import { loadQuestionView } from "./load-question";
import { QUESTIONS, plain, type QuestionView } from "./question-view";

const root = getRepoRoot();
const stored = JSON.parse(readFileSync(path.join(root, "companies/sun_pharma/company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json"), "utf8")).answers;
const LEAK = /\b[A-Z]{2,4}-\d{3,}\b|\b[A-Z]{3,}_[A-Z_]{3,}\b|UNABLE_TO|NO_OUTCOME/;

describe("Question experience — Sun Pharma", async () => {
  const views: Record<string, QuestionView> = {};
  for (const q of QUESTIONS) views[q.id] = (await loadQuestionView("sun-pharma", q.id))!;

  it("renders all five approved questions", () => {
    for (const q of QUESTIONS) {
      const v = views[q.id];
      expect(v, q.id).toBeTruthy();
      expect(v.conclusion.length).toBeGreaterThan(40);
      expect(v.facts.length).toBeGreaterThanOrEqual(3);
      if (!["what-has-management-promised", "what-did-management-actually-deliver"].includes(q.id)) expect(v.blocks.length).toBeGreaterThan(0); // commitment pages carry the approved answer and evidence drill-downs
    }
  });
  it("key facts match the stored approved answers", () => {
    const p = views["what-has-management-promised"].facts.map((f) => `${f.label}:${f.value}`).join("|");
    expect(p).toContain("Total management commitments tracked:46");
    expect(p).toContain("Hard commitments:3");
    expect(JSON.stringify(stored["what-has-management-promised"].answer.deterministic_precision_facts)).toContain("46");
    const r = views["what-could-go-wrong"].facts.map((f) => `${f.label}:${f.value}`).join("|");
    expect(r).toContain("Total tracked risk themes:20");
    expect(r).toContain("Currently worsening risks:2");
    expect(views["how-is-capital-allocated"].facts.some((f) => f.value === "₹3,609 Cr")).toBe(true);
  });
  it("leaks no internal IDs or machine codes anywhere, including the full original analysis", () => {
    for (const q of QUESTIONS) expect(JSON.stringify(views[q.id]), q.id).not.toMatch(LEAK);
  });
  it("keeps the full original analysis (every stored field present)", () => {
    for (const q of QUESTIONS) {
      const keys = new Set(views[q.id].drilldown.original.map((o) => o.label.toLowerCase()));
      for (const k of ["simple answer", "what evidence shows", "what is not yet proven", "what to monitor"]) expect(keys.has(k), `${q.id}/${k}`).toBe(true);
    }
  });
  it("every block is built from approved records; no comparison with unapproved analysis exists", () => {
    for (const q of QUESTIONS) for (const b of views[q.id].blocks) expect(JSON.stringify(b), `${q.id}/${b.id}`).not.toMatch(/shadow|unapproved|candidate/i);
  });
  it("Sun Pharma's register-based commitment views are withheld; the approved answers carry the commitment evidence", () => {
    for (const q of ["what-has-management-promised", "what-did-management-actually-deliver"]) expect(views[q].blocks.some((b) => b.id === "overview" || b.id === "chains")).toBe(false);
    expect(views["what-has-management-promised"].conclusion).toMatch(/three are hard commitments/i);
  });
  it("charts use correctly scoped data (risk spans within FY20–FY26; capital rows from the ledger)", () => {
    const spans = views["what-could-go-wrong"].blocks.find((b) => b.body.kind === "spans")!.body;
    if (spans.kind === "spans") for (const r of spans.rows) { expect(r.from).toBeGreaterThanOrEqual(spans.axis[0]); expect(r.to).toBeLessThanOrEqual(spans.axis[1]); expect(r.from).toBeLessThanOrEqual(r.to); }
    const cap = views["how-is-capital-allocated"].blocks[0].body;
    expect(cap.kind === "visual" && cap.visual.kind === "table" && cap.visual.rows.some((r) => r[0] === "Acquisitions" && r[3].includes("No outcome evidence"))).toBe(true);
  });
  it("makes no causal claims in the added presentation text", () => {
    for (const q of QUESTIONS) {
      const added = JSON.stringify([views[q.id].blocks, views[q.id].discoveries]);
      expect(added, q.id).not.toMatch(/\b(because of|caused by|led to|resulted in|thanks to|drove)\b/i);
    }
  });
  it("links only to existing question routes, anchors or the story", () => {
    const ids = QUESTIONS.map((q) => q.id);
    for (const q of QUESTIONS) for (const d of views[q.id].discoveries) for (const l of d.links)
      expect(l.href.startsWith("#") || ids.some((id) => l.href === `/company/sun-pharma/question/${id}`), l.href).toBe(true);
  });
  it("plain() translates codes without changing meaning", () => {
    expect(plain("Foreign-exchange risk (RG-0007, CURRENTLY_WORSENING FY21–FY26): exposure")).toBe("Foreign-exchange risk (currently worsening FY21–FY26): exposure");
    expect(plain("MC-0031 (Nidlegy™ EMA filing) had a target H1CY24 — unresolved, not MISSED")).toBe("Nidlegy™ EMA filing had a target H1 2024 — unresolved, not missed");
  });
  it("does not modify approved artifacts after activation (M54.13: pinned to the activated files)", () => {
    const f = path.join(root, "companies/sun_pharma/company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json");
    // M59.4 rewrote the served files and the registry (91 pairs); Sun's three M54.13 approvals are still registered at their activated digests
    const approvals = JSON.parse(readFileSync(path.join(root, "governance/approval_registry.json"), "utf8")).approvals;
    expect(approvals["sun_pharma:what-has-management-promised"].full_artifact_digest).toBe("02ed5ce98eae4dcd61a8bfa439243dbf7f7b2f65541845e76465640bde598c16");
    expect(approvals["sun_pharma:what-did-management-actually-deliver"].full_artifact_digest).toBe("820d8e38cf71766da0af9e47b347c89c4a92a248dc640095767c3bedc53e9f29");
    expect(approvals["sun_pharma:how-good-is-management"].full_artifact_digest).toBe("5a8a9d492fceff61016ab00d77d937f8d575ae50dfa9e9da282bc070621bcaee");
    expect(createHash("sha256").update(readFileSync(f)).digest("hex")).toBe("bd09be3f85ba57cf93226c7dee7c0ba3463b6664d6c9f898b575be428837f5d3");   // Sun served answers after M59.4
  });
});
