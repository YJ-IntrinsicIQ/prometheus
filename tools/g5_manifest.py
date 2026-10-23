#!/usr/bin/env python3
"""M63 / G5 — hash-pinned manifest of a scratch candidate: 91 original/proposed digests, projection ledgers, the RENDERED surfaces (every question view, Story, Panel specialist and
Explorer as the loaders return them), code and test files, claim inventory, review queue, protected-artifact snapshot. H3 covers all of them."""
import argparse
import glob
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def sha(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--supersedes", required=True)
    ap.add_argument("--tests", required=True)
    ap.add_argument("--protected-before", required=True)
    ap.add_argument("--protected-after", required=True)
    a = ap.parse_args()
    W = Path(a.work)
    rows = [json.loads(Path(f).read_text()) for f in sorted(glob.glob(str(W / "bundle/answers/*.json")))]
    answers = [{"slot": r["slot"], "base": r["report"]["base"], "original_full_digest": r["report"]["original"]["full_digest"], "proposed_full_digest": r["report"]["proposed"]["full_digest"],
                "proposed_content_fingerprint": r["report"]["proposed"]["content_fingerprint"], "changed_fields": r["report"]["changed_fields"]} for r in rows]
    surf = json.loads((W / "surf_pass2.json").read_text())
    rendered = {k: {s["name"]: hashlib.sha256(json.dumps(s["items"], sort_keys=True, ensure_ascii=False).encode()).hexdigest() for s in v} for k, v in surf.items()}
    led = {k: sha(W / f"root/companies/{k}/company_memory/ask_intrinsiciq/g5_absence_provenance.json") for k in ("sun_pharma", "tanla", "ujjivan", "datapatterns")}
    code = ["pipelines/g5_verify.py", "pipelines/g5_provenance.py", "pipelines/g4_investor_answers.py", "tools/g5_build_bundle.py", "tools/g5_build_sidecar.py", "tools/g5_clean_inventory.py", "tools/g5_prepare_bundle.sh",
            "tools/g5_manifest.py", "tools/g5_make_root.py", "tests/intelligence/test_g5_positive_claims.py", "tests/intelligence/test_g5_provenance_bundle.py", "apps/ask-intrinsiciq/src/lib/provenance/absence.test.ts", "tests/intelligence/test_g5_root_cause_repair.py", "tests/intelligence/test_g5_evidence_verification.py", "tests/fixtures/g5_mechanism_audit_cases.json",
            "apps/ask-intrinsiciq/src/lib/provenance/absence.ts", "apps/ask-intrinsiciq/src/lib/story/question-view.ts", "apps/ask-intrinsiciq/src/lib/story/load-story.ts", "apps/ask-intrinsiciq/src/lib/panel/load-panel.ts",
            "apps/ask-intrinsiciq/src/lib/catalog/load-explorer.ts", "apps/ask-intrinsiciq/src/lib/panel/build-panel.ts", "apps/ask-intrinsiciq/src/lib/provenance/customer-render.test.ts"]
    rendered_sha = hashlib.sha256(json.dumps(rendered, sort_keys=True).encode()).hexdigest()
    pb, pa = json.loads(Path(a.protected_before).read_text()), json.loads(Path(a.protected_after).read_text())
    body = {"supersedes": a.supersedes, "answers": answers, "ledgers_sha256": led, "rendered_surfaces_sha256": rendered_sha, "rendered_surfaces_by_company": rendered, "code_sha256": {c: sha(REPO / c) for c in code},
            "clean_inventory_sha256": sha(W / "clean_pass2.json"), "review_queue_sha256": sha(W / "review_queue.json"), "tests": json.loads(Path(a.tests).read_text()), "protected_before": pb, "protected_after": pa,
            "protected_changed": pb["tree_sha256"] != pa["tree_sha256"] or pb["single"] != pa["single"]}
    h = hashlib.sha256(json.dumps({k: body[k] for k in ("answers", "ledgers_sha256", "rendered_surfaces_sha256", "code_sha256", "clean_inventory_sha256", "review_queue_sha256")}, sort_keys=True).encode()).hexdigest()
    Path(a.out).write_text(json.dumps({"bundle_hash_H3": h, **body}, indent=1, ensure_ascii=False))
    print("H3", h, "rendered", rendered_sha[:16], "protected_changed", body["protected_changed"])


if __name__ == "__main__":
    main()
