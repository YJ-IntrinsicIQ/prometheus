#!/usr/bin/env python3
"""
M59.4 — coordinated, owner-authorized activation: the 71 new answers of the M59.3 manifest plus controlled reapproval of the six
corrected promises/delivery answers. No shortcut: every approval is recorded by answer_certification.mode_approve, the 71 go through
the existing m59_activate.py (manifest-sha256 guard), and any failure restores the backups taken at the start.

    python3 pipelines/m59_4_close.py                                   # preflight + full dry run, writes nothing
    python3 pipelines/m59_4_close.py --apply --owner-authorized "<note>"   # one coordinated change
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipelines import answer_certification as ac  # noqa: E402
from pipelines import pacp_adversarial as pa  # noqa: E402

MANIFEST_SHA = "43297f9c98842ff59660655d6bfa8f1b3ca519179930df80d875efc16583f0e0"
MANIFEST = ROOT / "preview" / "M59_3_FINAL_AUTHORIZATION_MANIFEST.json"
REGISTRY = ROOT / "governance" / "approval_registry.json"
COMPANIES = ["sun_pharma", "tanla", "ujjivan", "datapatterns"]
ALLOWED_WARNS = {"check_runtime_sanitizer_compat", "check_capital_no_unattributed_roi"}   # both documented, non-blocking (fail safe by omission / false positive on 'Return on capital employed' in a monitor item)
served = lambda c: ac.companies_root() / c / "company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json"  # noqa: E731
cand = lambda c: ac.companies_root() / c / "company_memory/ask_intrinsiciq/m59_candidate_answers.json"  # noqa: E731
repl = lambda c: ac.companies_root() / c / "company_memory/ask_intrinsiciq/m59_3_replacement_candidates.json"  # noqa: E731
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()  # noqa: E731


def preflight() -> tuple[list[str], dict]:
    bad: list[str] = []
    info: dict = {}
    if sha(MANIFEST) != MANIFEST_SHA:
        bad.append(f"manifest sha256 {sha(MANIFEST)} != authorized {MANIFEST_SHA}")
        return bad, info
    man = json.loads(MANIFEST.read_text())
    registry = json.loads(REGISTRY.read_text())["approvals"]
    info["registry_before"] = len(registry)
    # 2. the 71 new answers
    files = {c: json.loads(cand(c).read_text())["answers"] for c in COMPANIES}
    for e in man["pairs"]:
        a = files[e["company"]].get(e["question_id"])
        key = f"{e['company']}:{e['question_id']}"
        if not a:
            bad.append(f"{key}: candidate missing"); continue
        if ac.compute_full_artifact_digest(a["answer"]) != e["full_artifact_digest"] or ac.compute_content_fingerprint(a["answer"]) != e["fingerprint"]:
            bad.append(f"{key}: digest/fingerprint differs from the manifest")
        if key in registry:
            bad.append(f"{key}: already registered")
        r = pa.run_adversarial_suite(a["answer"], e["company"], e["question_id"])
        if r["fails"] or not set(r["warns"]) <= ALLOWED_WARNS:
            bad.append(f"{key}: PACP fails={r['fails']} warns={r['warns']}")
    info["new"] = len(man["pairs"])
    if len(man["pairs"]) != 71:
        bad.append(f"manifest has {len(man['pairs'])} pairs, expected 71")
    extra = {(c, q) for c in COMPANIES for q in files[c]} - {(e["company"], e["question_id"]) for e in man["pairs"]}
    if extra:
        bad.append(f"candidate files hold pairs outside the manifest: {sorted(extra)}")
    # 5. exclusions stay excluded
    for x in man["excluded"]:
        key = f"{x['company']}:{x['question_id']}"
        if x["question_id"] in files[x["company"]] or key in registry or x["question_id"] in json.loads(served(x["company"]).read_text())["answers"]:
            bad.append(f"{key}: excluded but present")
    info["excluded"] = len(man["excluded"])
    # 3 + 4. six replacements and their originals
    reps = man["approved_answers_needing_separate_correction"]
    if len(reps) != 6:
        bad.append(f"{len(reps)} replacements listed, expected 6")
    for r in reps:
        c, q = r["company"], r["question_id"]
        key = f"{c}:{q}"
        cur = json.loads(served(c).read_text())["answers"][q]["answer"]
        rec = registry.get(key, {})
        if not (ac.compute_full_artifact_digest(cur) == rec.get("full_artifact_digest") == r["approved_digest"]):
            bad.append(f"{key}: current served answer does not match its registered digest")
        doc = json.loads(repl(c).read_text())["answers"][q]
        new = doc["answer"]
        if ac.compute_full_artifact_digest(new) != r["replacement_digest"] or ac.compute_content_fingerprint(new) != r["replacement_fingerprint"]:
            bad.append(f"{key}: replacement digest differs from the manifest")
        if doc["supersedes"]["full_artifact_digest"] != rec.get("full_artifact_digest"):
            bad.append(f"{key}: replacement supersedes a different digest")
        s = pa.run_adversarial_suite(new, c, q)
        if s["fails"] or s["overall"] not in ("PASS", "WARN") or not set(s["warns"]) <= ALLOWED_WARNS:
            bad.append(f"{key}: replacement PACP {s['overall']} fails={s['fails']} warns={s['warns']}")
    info["replacements"] = len(reps)
    # Ujjivan provenance: no FY26 filing exists locally; no candidate may claim FY26 evidence
    uj = sorted(p.name for p in (ROOT / "data/Processed/ujjivan").glob("fy*"))
    info["ujjivan_local_years"] = uj
    if "fy26" in uj:
        info["ujjivan_note"] = "an FY26 folder exists locally — revisit provenance"
    for e in man["pairs"]:
        if e["company"] == "ujjivan":
            t = json.dumps(files["ujjivan"][e["question_id"]]["answer"], ensure_ascii=False)
            if "fy26" not in uj and __import__("re").search(r"FY26 (annual )?report (shows|states|reports|gives|cites)", t):
                bad.append(f"ujjivan:{e['question_id']}: claims FY26 report evidence that is not held locally")
    # proposed registry state
    proposed = set(registry) | {f"{e['company']}:{e['question_id']}" for e in man["pairs"]}
    info["proposed_total"] = len(proposed)
    if len(proposed) != 91:
        bad.append(f"proposed registry would hold {len(proposed)} pairs, expected 91")
    return bad, info


def backup() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    d = ROOT / "governance" / f"m594_backup_{stamp}"
    d.mkdir()
    shutil.copy2(REGISTRY, d / "approval_registry.json")
    for c in COMPANIES:
        shutil.copy2(served(c), d / f"{c}__shadow_level3_hybrid_answers.json")
    (d / "sha256.json").write_text(json.dumps({"approval_registry.json": sha(REGISTRY), **{c: sha(served(c)) for c in COMPANIES}}, indent=2))
    return d


def restore(d: Path) -> bool:
    shutil.copy2(d / "approval_registry.json", REGISTRY)
    for c in COMPANIES:
        shutil.copy2(d / f"{c}__shadow_level3_hybrid_answers.json", served(c))
    want = json.loads((d / "sha256.json").read_text())
    return sha(REGISTRY) == want["approval_registry.json"] and all(sha(served(c)) == want[c] for c in COMPANIES)


def replace_six(note: str, man: dict) -> None:
    pairs = []
    for r in man["approved_answers_needing_separate_correction"]:
        c, q = r["company"], r["question_id"]
        new = json.loads(repl(c).read_text())["answers"][q]
        doc = json.loads(served(c).read_text())
        entry = doc["answers"][q]
        entry["answer"] = new["answer"]
        entry["word_count"] = new["word_count"]
        entry["m594_supersedes"] = r["approved_digest"]
        served(c).write_text(json.dumps(doc, indent=2, ensure_ascii=False))
        pairs.append(f"{c}:{q}")
    ac.mode_approve(",".join(pairs), note + " | controlled reapproval: " + ";".join(f"{p}@{r['replacement_digest'][:12]}<-{r['approved_digest'][:12]}" for p, r in zip(pairs, man["approved_answers_needing_separate_correction"])))


def verify(man: dict, before: dict) -> list[str]:
    bad = []
    reg = json.loads(REGISTRY.read_text())["approvals"]
    for e in man["pairs"]:
        k = f"{e['company']}:{e['question_id']}"
        if reg.get(k, {}).get("full_artifact_digest") != e["full_artifact_digest"] or reg[k].get("fingerprint") != e["fingerprint"]:
            bad.append(f"{k}: registered digest differs")
    replaced = {f"{r['company']}:{r['question_id']}": r for r in man["approved_answers_needing_separate_correction"]}
    for k, r in replaced.items():
        if reg.get(k, {}).get("full_artifact_digest") != r["replacement_digest"]:
            bad.append(f"{k}: replacement not registered")
    for k, rec in before.items():
        if k not in replaced and reg.get(k) != rec:
            bad.append(f"{k}: existing approval changed")
    for c in COMPANIES:
        doc = json.loads(served(c).read_text())["answers"]
        for k, rec in reg.items():
            cc, q = k.split(":")
            if cc == c and ac.compute_full_artifact_digest(doc[q]["answer"]) != rec["full_artifact_digest"]:
                bad.append(f"{k}: served answer does not match its registered digest")
    if len(reg) != 91:
        bad.append(f"registry holds {len(reg)} pairs, expected 91")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--owner-authorized", default="")
    ap.add_argument("--simulate-failure", action="store_true", help="rehearsal only: fail after the first stage to prove the restore")
    ap.add_argument("--companies-root", required=True, type=Path, help="absolute company-data root (required; no default)")
    ap.add_argument("--authorize-served-write", action="store_true", help="permit --companies-root to be the served companies/ tree")
    a = ap.parse_args()
    ac.configure_companies_root(a.companies_root, authorize_served=a.authorize_served_write)
    bad, info = preflight()
    print("PREFLIGHT", "FAILED" if bad else "PASSED", json.dumps(info))
    for b in bad:
        print("  !", b)
    if bad:
        return 3
    man = json.loads(MANIFEST.read_text())
    dry = subprocess.run([sys.executable, str(ROOT / "pipelines/m59_activate.py"), "--families", "all"], capture_output=True, text=True, cwd=ROOT)
    print(dry.stdout.splitlines()[0], "|", "DRY RUN" if "DRY RUN" in dry.stdout else "NO DRY RUN")
    if dry.returncode != 0 or "71 eligible; 0 refused" not in dry.stdout:
        print("  ! activation dry run did not select exactly the 71 eligible pairs"); return 3
    if not a.apply:
        print("DRY RUN — nothing written. 6 replacements would be reapproved after the 71 new answers.")
        return 0
    if not a.owner_authorized.strip():
        print("REFUSED: --apply needs --owner-authorized"); return 2
    before = json.loads(REGISTRY.read_text())["approvals"]
    bdir = backup()
    print("backup:", bdir.relative_to(ROOT))
    try:
        r = subprocess.run([sys.executable, str(ROOT / "pipelines/m59_activate.py"), "--families", "all", "--owner-authorized", a.owner_authorized, "--manifest-sha256", MANIFEST_SHA, "--apply"], capture_output=True, text=True, cwd=ROOT)
        print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:])
        if r.returncode != 0:
            raise RuntimeError(f"activation of the 71 failed (exit {r.returncode})")
        if a.simulate_failure:
            raise RuntimeError("simulated failure after the 71 were activated")
        replace_six(a.owner_authorized, man)
        problems = verify(man, before)
        if problems:
            raise RuntimeError("; ".join(problems[:5]))
    except Exception as exc:  # noqa: BLE001
        ok = restore(bdir)
        print(f"FAILED: {exc}\nRESTORED from {bdir.relative_to(ROOT)}: original state {'confirmed' if ok else 'NOT CONFIRMED'}")
        return 1
    print(f"ACTIVATED 71 and REPLACED 6; registry {len(json.loads(REGISTRY.read_text())['approvals'])} pairs; backup {bdir.relative_to(ROOT)}")
    print("registry sha256", sha(REGISTRY)); print("sun served sha256", sha(served('sun_pharma')))
    return 0


if __name__ == "__main__":
    sys.exit(main())
