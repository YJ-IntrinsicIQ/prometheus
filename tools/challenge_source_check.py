"""Verifies every challenge-case source quote against the ORIGINAL filing PDF page (1-based). Read-only, no AI.
Usage: python3 -I tools/challenge_source_check.py [cases.json]   -> exit 1 if any quote is not on its stated page.
The optional path lets an independent reviewer validate a sealed holdout file; the implementer must never run it on that file."""
import json, re, sys, pathlib
import pymupdf
ROOT = pathlib.Path(__file__).resolve().parents[1]
cases = json.loads(pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "tests/challenge/cases.json").read_text())
cases = cases["cases"] + cases.get("observations", [])
cache = {}
def page_text(company, fy, page):
    key = (company, fy)
    if key not in cache:
        pdf = ROOT / f"data/Processed/{company}/{fy}/annual_report/{company}_{fy}.pdf"
        cache[key] = [p.get_text() for p in pymupdf.open(pdf)]
    t = cache[key]
    return t[page - 1] if 0 < page <= len(t) else ""
bad = 0
for c in cases:
    for s in c["source"]:
        if s.get("kind") == "internal":
            print(f"{c['id']:6} internal   {s['note'][:70]}"); continue
        ok = bool(re.search(s["quote"], page_text(s["company"], s["fy"], s["page"])))
        bad += not ok
        print(f"{c['id']:6} {'OK ' if ok else 'BAD'} {s['company']} {s['fy']} p.{s['page']} /{s['quote']}/")
sys.exit(1 if bad else 0)
