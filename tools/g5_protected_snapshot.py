#!/usr/bin/env python3
"""Content snapshot of the protected artifacts: every file under companies/ and governance/ (BACKLOG.md, SESSION_LOG.md and .DS_Store excluded) plus the named single files.
Run before and after a mission; identical output = nothing protected changed. Read-only."""
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SINGLE = ["governance/approval_registry.json", "intelligence/management_quality/fact_pack_v2.py", "tests/challenge/baseline.json", "tests/challenge/cases.json", "tests/challenge/negative_claims_review.json"] + \
         [f"companies/{k}/company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json" for k in ("sun_pharma", "tanla", "ujjivan", "datapatterns")]


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    files = sorted(p for root in ("companies", "governance") for p in (REPO / root).rglob("*") if p.is_file() and p.name not in ("BACKLOG.md", "SESSION_LOG.md", ".DS_Store"))
    tree = hashlib.sha256()
    for p in files:
        tree.update(f"{p.relative_to(REPO)}\0{sha(p)}\n".encode())
    out = {"files": len(files), "tree_sha256": tree.hexdigest(), "single": {s: sha(REPO / s) for s in SINGLE if (REPO / s).exists()},
           "approvals": len(json.loads((REPO / "governance/approval_registry.json").read_text())["approvals"])}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
