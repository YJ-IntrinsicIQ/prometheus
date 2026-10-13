#!/usr/bin/env python3
"""M63 / G5 — isolated sandbox root for rehearsal (never touches the repository). Copies a base evidence root (a symlink farm plus overlays), replaces the protected
ask_intrinsiciq folders and the governance folder with real directories of links, installs the bundle's 91 replacement answers into COPIES of the hybrid answer files and
re-pins a COPY of the approval registry to their digests. The repository's registry and served files are only read."""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from pipelines.answer_certification import compute_content_fingerprint, compute_full_artifact_digest  # noqa: E402


def real_dir_of_links(link: Path) -> Path:
    """Replace a symlinked directory by a real directory holding a symlink to each entry (so single files can then be replaced locally)."""
    target = Path(os.path.realpath(link))
    if link.is_symlink():
        link.unlink()
    link.mkdir(parents=True, exist_ok=True)
    for child in target.iterdir():
        dst = link / child.name
        if not dst.exists():
            dst.symlink_to(child)
    return link


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(a.base, out, symlinks=True)
    gov = real_dir_of_links(out / "governance")
    reg = json.loads((REPO / "governance" / "approval_registry.json").read_text())
    reg_path = gov / "approval_registry.json"
    reg_path.unlink()
    n = 0
    for f in sorted((Path(a.bundle) / "answers").glob("*.json")):
        d = json.loads(f.read_text())
        slot, ans = d["slot"], d["answer"]
        key, qid = slot.split(":", 1)
        mem = real_dir_of_links(out / "companies" / key / "company_memory" / "ask_intrinsiciq")
        hp = mem / "shadow_level3_hybrid_answers.json"
        if hp.is_symlink():
            data = json.loads(hp.read_text())
            hp.unlink()
            hp.write_text(json.dumps(data))
        data = json.loads(hp.read_text())
        data["answers"][qid]["answer"] = ans
        hp.write_text(json.dumps(data))
        rec = reg["approvals"][slot]
        rec["fingerprint"] = compute_content_fingerprint(ans)
        rec["full_artifact_digest"] = compute_full_artifact_digest(ans)
        n += 1
    reg_path.write_text(json.dumps(reg, indent=1))
    print("sandbox", out, "answers installed", n)


if __name__ == "__main__":
    main()
