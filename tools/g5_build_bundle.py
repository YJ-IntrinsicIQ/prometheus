#!/usr/bin/env python3
"""M63 / G5 — scratch replacement bundle for the 91 approved answer slots (read-only on the repository; writes only under --out). Zero AI calls.

For every approved slot: base = the repaired G4/G5 candidate when one exists for that slot, otherwise the approved answer itself; then the shared provenance mechanism
(pipelines/g5_provenance.annotate_answer) rewrites only the clauses the evidence contradicts and adds claim-linked absence entries and a pending-review list.
Nothing here touches governance/ or companies/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from pipelines import g4_investor_answers as g4  # noqa: E402
from pipelines import g5_provenance as G  # noqa: E402
from pipelines import m59_question_batch as m59  # noqa: E402
from pipelines.answer_certification import compute_content_fingerprint, compute_full_artifact_digest  # noqa: E402

def norm(o):
    """Integral floats become ints (value-preserving): the app computes its integrity digests in JavaScript, which prints 64.0 as 64."""
    if isinstance(o, float) and o.is_integer():
        return int(o)
    if isinstance(o, dict):
        return {k: norm(v) for k, v in o.items()}
    return [norm(v) for v in o] if isinstance(o, list) else o


NUM = re.compile(r"\d[\d,]*\.?\d*")


def numbers_in(a: dict) -> set[float]:
    out: set[float] = set()
    for _, _, t in G._text_fields(a):
        out |= {float(x.replace(",", "")) for x in NUM.findall(t) if x.replace(",", "").replace(".", "", 1).isdigit()}
    for d in a.get("deterministic_precision_facts") or []:
        out |= {float(x.replace(",", "")) for x in NUM.findall(str(d)) if x.replace(",", "").replace(".", "", 1).isdigit()}
    return out


def validate(co, qid: str, a: dict) -> list[str]:
    mask = lambda t: re.sub(r"“[^”]*”", "“[filing text]”", t) if isinstance(t, str) else t
    ma = dict(a)
    for f in ("simple_answer", "what_may_mean_economically", "what_is_not_yet_proven"):
        ma[f] = mask(a.get(f))
    for f in ("what_evidence_shows", "what_to_monitor", "key_points"):
        ma[f] = [mask(x) for x in a.get(f, [])]
    return list(m59.validate(ma, co, qid, numbers_in(a))["failed"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--cand", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    (out / "answers").mkdir(parents=True, exist_ok=True)
    registry = json.loads((REPO / "governance" / "approval_registry.json").read_text())["approvals"]
    cand_slots = {(k, q) for k in m59.COMPANIES for q in g4.QUESTION_FOR_AREA.values() if (Path(args.cand) / f"{k}__{q}.candidate.json").exists()}
    slots, rows = [], []
    for k in m59.COMPANIES:
        L = g4.Ledger(k, Path(args.root))
        co = m59.Co(k, registry)
        for slot in sorted(r for r in registry if r.startswith(k + ":")):
            qid = slot.split(":", 1)[1]
            orig = co.approved(qid)
            base_kind = "approved"
            base = orig
            if (k, qid) in cand_slots:
                base = json.loads((Path(args.cand) / f"{k}__{qid}.candidate.json").read_text())["answer"]
                base_kind = "g4_g5_candidate"
            new, rep = G.annotate_answer(L, base)
            if m59.words(new) > max(600, m59.words(orig)):
                new, rep = G.annotate_answer(L, base, compact=True)
            new = norm(new)
            f_orig, f_new = validate(co, qid, orig), validate(co, qid, new)
            changed = sorted(c for c in set(new) | set(orig) if new.get(c) != orig.get(c))      # every top-level field, so no investor-visible change goes unlisted
            row = {"slot": slot, "company": k, "question_id": qid, "base": base_kind,
                   "original": {"content_fingerprint": compute_content_fingerprint(orig), "full_digest": compute_full_artifact_digest(orig), "registry_fingerprint": registry[slot].get("fingerprint")},
                   "proposed": {"content_fingerprint": compute_content_fingerprint(new), "full_digest": compute_full_artifact_digest(new)},
                   "changed_fields": changed, "rewrites": rep["changes"], "entries": rep["entries"], "pending": rep["pending"], "scoped_statements": rep["scoped"], "system_statements": rep["system"],
                   "validator_failed_original": f_orig, "validator_failed_proposed": f_new, "validator_regression": sorted(set(f_new) - set(f_orig)),
                   "words_original": m59.words(orig), "words_proposed": m59.words(new),
                   "unresolved_evidence_questions": sorted({p["review"] or p["status"] for p in new.get("g5_review_pending", [])})}
            (out / "answers" / f"{k}__{qid}.json").write_text(json.dumps({"slot": slot, "answer": new, "report": row}, ensure_ascii=False, indent=1, sort_keys=True))
            rows.append(row)
    manifest = {"slots": len(rows), "answers": rows,
                "code": {p: hashlib.sha256((REPO / p).read_bytes()).hexdigest() for p in ("pipelines/g4_investor_answers.py", "pipelines/g5_provenance.py", "tools/g5_build_bundle.py", "tools/g5_clean_inventory.py")}}
    (out / "answers_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    reg_regress = [r["slot"] for r in rows if r["validator_regression"]]
    print("slots", len(rows), "candidate-based", sum(r["base"] != "approved" for r in rows), "rewritten", sum(bool(r["rewrites"]) for r in rows), "with pending", sum(bool(r["pending"]) for r in rows), "validator regressions", reg_regress)


if __name__ == "__main__":
    main()
