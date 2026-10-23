#!/usr/bin/env python3
"""Evidence root for the G5 pipeline: a symlink farm over the repository in which the candidate financial / commitment artifacts built by tools/g1_candidate_build.py replace the
served ones. Nothing under the repository is written; the farm and the candidate output live in scratch. Usage: g5_make_root.py <candidate_out> <root>"""
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OVERRIDE_FY = ("financials", "intelligence")
OVERRIDE_MEM = ("financials", "capital_allocation_outcomes", "economic_attribution", "management_commitments", "management_progression", "gold")


def link_all(src: Path, dst: Path, skip=()) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for c in src.iterdir():
        if c.name in skip or (dst / c.name).exists():
            continue
        (dst / c.name).symlink_to(c)


def main(cand: str, root: str) -> None:
    cand, root = Path(cand), Path(root)
    if root.exists():
        shutil.rmtree(root)
    link_all(REPO, root, skip=("companies",))
    for co in sorted(p for p in (REPO / "companies").iterdir() if p.is_dir()):
        dst = root / "companies" / co.name
        cc = cand / "companies" / co.name
        if not cc.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.symlink_to(co)
            continue
        dst.mkdir(parents=True, exist_ok=True)
        for child in co.iterdir():
            t = dst / child.name
            if child.name == "company_memory":
                t.mkdir()
                for m in child.iterdir():
                    (t / m.name).symlink_to(cc / "company_memory" / m.name if m.name in OVERRIDE_MEM and (cc / "company_memory" / m.name).exists() else m)
            elif child.name.startswith("fy") and child.is_dir():
                t.mkdir()
                for e in child.iterdir():
                    (t / e.name).symlink_to(cc / child.name / e.name if e.name in OVERRIDE_FY and (cc / child.name / e.name).exists() else e)
            else:
                t.symlink_to(child)
    print("root", root)


if __name__ == "__main__":
    main(*sys.argv[1:3])
