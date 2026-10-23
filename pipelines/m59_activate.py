#!/usr/bin/env python3
"""
M59 — owner-authorized activation of reviewed candidates. NOT RUN BY THE BATCH. Default is a dry run.

    python3 pipelines/m59_activate.py --families financials,understand-the-business --owner-authorized "<your approval note>"          # dry run
    python3 pipelines/m59_activate.py --families financials --owner-authorized "<note>" --apply                                          # activate

For each selected READY candidate it (1) re-verifies the exact digest recorded in the review package, (2) backs up the
served-answers file and the registry, (3) copies ONLY that answer into the served file, and (4) records the approval through
the existing workflow (answer_certification.mode_approve). It refuses to touch any pair that is already registered, and it
refuses if a digest differs from the package. Without --owner-authorized and --apply, nothing is written.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipelines import answer_certification as ac  # noqa: E402

COMPANIES = ["sun_pharma", "tanla", "ujjivan", "datapatterns"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--families", required=True, help="comma-separated catalog family ids, or 'all'")
    ap.add_argument("--companies", default="all")
    ap.add_argument("--questions", default="all", help="comma-separated question ids, or 'all'")
    ap.add_argument("--owner-authorized", default="", help="the owner's authorization note (required to apply)")
    ap.add_argument("--manifest-sha256", default="", help="sha256 of the final authorization manifest the owner approved (required with --apply)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--companies-root", required=True, type=Path, help="absolute company-data root (required; no default)")
    ap.add_argument("--authorize-served-write", action="store_true", help="permit --companies-root to be the served companies/ tree")
    a = ap.parse_args()
    ac.configure_companies_root(a.companies_root, authorize_served=a.authorize_served_write, read_only=not a.apply)   # a dry run only reads

    pairs = json.loads((ROOT / "preview" / "M59_pairs.json").read_text())["pairs"]
    fams = None if a.families == "all" else set(a.families.split(","))
    cos = COMPANIES if a.companies == "all" else a.companies.split(",")
    qs = None if a.questions == "all" else set(a.questions.split(","))
    registry = json.loads((ROOT / "governance" / "approval_registry.json").read_text())["approvals"]
    chosen = [p for p in pairs if p["status"] == "READY" and (fams is None or p["family"] in fams) and p["company"] in cos and (qs is None or p["question_id"] in qs)]
    problems: list[str] = []
    plan: list[tuple[dict, dict]] = []
    # M59.2: when a final authorization manifest exists, only the exact (company, question, digest, fingerprint) it lists may be activated
    final = ROOT / "preview" / "M59_3_FINAL_AUTHORIZATION_MANIFEST.json"
    allowed = {(e["company"], e["question_id"]): (e["full_artifact_digest"], e["fingerprint"]) for e in json.loads(final.read_text())["pairs"]} if final.exists() else None
    for p in chosen:
        key = f"{p['company']}:{p['question_id']}"
        if allowed is not None and allowed.get((p["company"], p["question_id"])) != (p["full_artifact_digest"], p["fingerprint"]):
            problems.append(f"{key}: not in (or differs from) the final authorization manifest — refusing")
            continue
        if key in registry:
            problems.append(f"{key}: already registered — not touched")
            continue
        cand_file = json.loads((ac.companies_root() / p["company"] / "company_memory/ask_intrinsiciq/m59_candidate_answers.json").read_text())
        entry = cand_file["answers"].get(p["question_id"])
        if not entry:
            problems.append(f"{key}: no candidate in the candidate file")
            continue
        if ac.compute_full_artifact_digest(entry["answer"]) != p["full_artifact_digest"] or ac.compute_content_fingerprint(entry["answer"]) != p["fingerprint"]:
            problems.append(f"{key}: candidate differs from the digest in the review package — refusing")
            continue
        plan.append((p, entry))
    print(f"selected {len(chosen)} READY pairs; {len(plan)} eligible; {len(problems)} refused/skipped")
    for pr in problems:
        print("  !", pr)
    for p, _ in plan[:200]:
        print(f"  + {p['company']}:{p['question_id']}  digest {p['full_artifact_digest'][:16]}…")
    if not a.apply:
        print("\nDRY RUN — nothing written.")
        return 0
    if allowed is not None:
        import hashlib
        actual = hashlib.sha256(final.read_bytes()).hexdigest()
        if a.manifest_sha256 != actual:
            print(f"\nREFUSED: --manifest-sha256 must equal the approved manifest's sha256 ({actual}).")
            return 2
    if not a.owner_authorized.strip() or problems:
        print("\nREFUSED: --apply needs --owner-authorized and no refused pairs." if not a.owner_authorized.strip() else "\nREFUSED: resolve the refused pairs first (narrow --questions/--companies).")
        return 2
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    reg_path = ROOT / "governance" / "approval_registry.json"
    shutil.copyfile(reg_path, reg_path.with_name(f"approval_registry.pre_m59_{stamp}.json"))
    for co in sorted({p["company"] for p, _ in plan}):
        sp = ac.companies_root() / co / "company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json"
        shutil.copyfile(sp, sp.with_name(f"shadow_level3_hybrid_answers.pre_m59_{stamp}.json"))
        doc = json.loads(sp.read_text())
        for p, entry in plan:
            if p["company"] == co:
                doc["answers"][p["question_id"]] = {"question_id": p["question_id"], "answer": entry["answer"], "status": "PASS", "coverage": "COMPLETE", "word_count": entry["word_count"]}
        sp.write_text(json.dumps(doc, indent=2, ensure_ascii=False))
    batch = ",".join(f"{p['company']}:{p['question_id']}" for p, _ in plan)
    note = f"M59 owner-authorized: {a.owner_authorized.strip()} | digests " + ";".join(f"{p['question_id']}@{p['company']}={p['full_artifact_digest'][:12]}" for p, _ in plan)
    ac.mode_approve(batch, note)
    reg = json.loads(reg_path.read_text())["approvals"]
    bad = [f"{p['company']}:{p['question_id']}" for p, _ in plan if reg.get(f"{p['company']}:{p['question_id']}", {}).get("full_artifact_digest") != p["full_artifact_digest"]]
    print("\nACTIVATED" if not bad else f"\nDIGEST MISMATCH after approval: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
