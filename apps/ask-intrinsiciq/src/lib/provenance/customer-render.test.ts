// M63/G5: what the investor actually sees. Runs on whatever repository root the environment points at; when that root carries a G5 claim ledger (the sandbox candidate), every
// approved question, the Story, each Panel specialist and the Explorer must (1) show no unsupported definitive sentence from the ledger and (2) expose no internal verification key.
import { describe, expect, it } from "vitest";
import { loadExplorer } from "@/src/lib/catalog/load-explorer";
import { loadPanel } from "@/src/lib/panel/load-panel";
import { COMPANIES } from "@/src/lib/story/companies";
import { loadApprovedAnswers } from "@/src/lib/story/approved-answers";
import { loadQuestionView } from "@/src/lib/story/load-question";
import { loadStory } from "@/src/lib/story/load-story";
import { loadAbsenceLedger, INTERNAL_KEY } from "./absence";

const strings = (v: unknown, out: string[] = []): string[] => {
  if (typeof v === "string") out.push(v);
  else if (Array.isArray(v)) v.forEach((x) => strings(x, out));
  else if (v && typeof v === "object") Object.values(v).forEach((x) => strings(x, out));
  return out;
};
const keys = (v: unknown, out: string[] = []): string[] => {
  if (Array.isArray(v)) v.forEach((x) => keys(x, out));
  else if (v && typeof v === "object") for (const [k, x] of Object.entries(v)) { out.push(k); keys(x, out); }
  return out;
};
const INTERNAL_TEXT = /\bUNRESOLVED\b|\bNOT_EXTRACTED\b|\bNOT_DISCLOSED\b|\bNOT_APPLICABLE\b|PENDING_HUMAN|UNVERIFIED_SCOPED|replaces_status|evidence_group|\bg5_|\bg4_/;

describe("customer-facing render path (all companies)", async () => {
  for (const [slug] of Object.entries(COMPANIES)) {
    const ledger = await loadAbsenceLedger(slug);
    const unsafe = ledger.filter((e) => e.replacement && e.verification !== "VERIFIED" && !e.record_statement_ok);
    const views = await Promise.all(Object.keys(await loadApprovedAnswers(slug)).map((q) => loadQuestionView(slug, q)));
    const story = await loadStory(slug);
    const panel = await loadPanel(slug);
    const explorer = await loadExplorer(slug);
    it(`${slug}: question views expose no internal verification keys or labels (including the original-analysis drilldown)`, () => {
      for (const v of views) {
        if (!v) continue;
        expect(v.drilldown.original.map((o) => o.label.toLowerCase().replace(/ /g, "_")).filter((k) => INTERNAL_KEY.test(k))).toEqual([]);
        expect(strings(v.drilldown.original).filter((t) => INTERNAL_TEXT.test(t)).slice(0, 2)).toEqual([]);
      }
    });
    it(`${slug}: no unsupported definitive sentence from the ledger survives on Story, Panel or Explorer`, () => {
      const surfaces = [story, ...(panel?.specialists ?? []), explorer].filter(Boolean);
      for (const s of surfaces) {
        const text = strings(s);
        for (const e of unsafe) {
          if (e.anchor && e.anchor !== e.claim) continue;      // a labelled table cell is carried as metadata only
          expect(text.some((t) => t.includes(e.sentence ?? e.claim)), `${slug}: ${e.claim.slice(0, 60)}`).toBe(false);
        }
      }
    });
    it(`${slug}: no investor-facing key starts with an internal prefix outside the audit ledger`, () => {
      for (const s of [story, ...(panel?.specialists ?? []), explorer].filter(Boolean)) {
        const k = keys(s).filter((x) => INTERNAL_KEY.test(x));
        expect(k).toEqual([]);
      }
    });
  }
});
