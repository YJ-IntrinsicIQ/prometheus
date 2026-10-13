import { computeAnswerFingerprint, computeFullArtifactDigest } from "@/src/lib/ask-intrinsiciq/load-answer-card";

type Rec = { status?: string; fingerprint?: string; full_artifact_digest?: string | null } | undefined;
type Entry = { status?: string; coverage?: string; answer?: Record<string, unknown> } | undefined;

const BLOCKED = new Set(["PENDING_INDEPENDENT_REVIEW", "PENDING_MIGRATION_REVIEW", "REVOKED"]);

/**
 * The same gates the production hybrid loader applies (PASS/COMPLETE, approval record, status, fingerprint,
 * full-artifact digest). Read-only; fails closed with a reason.
 */
export function approvalGate(entry: Entry, record: Rec): { ok: boolean; reason: string } {
  if (!entry?.answer) return { ok: false, reason: "no stored answer" };
  if (entry.status !== "PASS" || entry.coverage !== "COMPLETE") return { ok: false, reason: "answer is not PASS/COMPLETE" };
  if (!record) return { ok: false, reason: "no approval record" };
  if (record.status && BLOCKED.has(record.status)) return { ok: false, reason: `approval status ${record.status}` };
  if (computeAnswerFingerprint(entry.answer) !== record.fingerprint) return { ok: false, reason: "fingerprint changed since approval" };
  if (record.full_artifact_digest && computeFullArtifactDigest(entry.answer) !== record.full_artifact_digest) return { ok: false, reason: "artifact digest changed since approval" };
  return { ok: true, reason: "approved" };
}
