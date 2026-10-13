"""Classifies the negative-claim inventory with tests/challenge/negative_claims_review.json (first matching rule wins)."""
import json, re, pathlib, collections, sys
R = pathlib.Path(__file__).resolve().parents[1]
inv = json.loads((R / "preview/m63_g0_negative_claims.json").read_text())
rules = json.loads((R / "tests/challenge/negative_claims_review.json").read_text())["rules"]
def classify(company, st):
    for r in rules:
        if r.get("companies") and company not in r["companies"]: continue
        if re.search(r["match"], st, re.I): return r["class"]
occ = collections.Counter(); uniq = collections.defaultdict(set); per = collections.defaultdict(collections.Counter)
for it in inv["items"]:
    c = classify(it["company"], it["statement"]); occ[c] += 1; uniq[c].add((it["company"], it["statement"])); per[it["company"]][c] += 1
out = {"occurrences": inv["count"], "unique": inv["unique"], "by_class": {k: {"occurrences": occ[k], "unique": len(uniq[k])} for k in sorted(occ)}, "by_company": {c: dict(v) for c, v in per.items()}}
(R / "preview/m63_g0_negative_claims_summary.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
