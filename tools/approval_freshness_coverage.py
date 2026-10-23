"""Planning-only freshness impact of a candidate on the approved answers: which approvals have changed dependencies, and for which approved ids the evaluator has no result.

Legacy approved ids ("what-could-go-wrong", "what-did-management-actually-deliver") predate the evaluator's question ids. The dependency registry records the correspondence itself, in
each question's `shadow_family_note` ("Shadow canary version (what-did-management-actually-deliver) ..."); this tool reads that governed note - it invents no alias - and reports every
approval as COVERED_DIRECT, COVERED_VIA_REGISTRY_ALIAS or UNCOVERED. No AI call, no write to governance, no answer mutation.

Usage: python3 tools/approval_freshness_coverage.py <companies_root> <out.json>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from intelligence.shadow_change_detector import evaluate_all_questions   # noqa: E402

_NOTE_ALIAS = re.compile(r"\(([a-z][a-z0-9\-]+)\)")


def registry_aliases(registry: Dict[str, Any]) -> Dict[str, str]:
    """legacy approved id -> evaluator question id, from the registry's own shadow_family_note."""
    out: Dict[str, str] = {}
    for question_id, entry in (registry.get("questions") or {}).items():
        match = _NOTE_ALIAS.search(str((entry or {}).get("shadow_family_note") or ""))
        if match and match.group(1) != question_id:
            out[match.group(1)] = question_id
    return out


def coverage(companies_root: str) -> Dict[str, Any]:
    approvals = json.loads((ROOT / "governance" / "approval_registry.json").read_text(encoding="utf-8"))["approvals"]
    registry = json.loads((ROOT / "governance" / "answer_dependency_registry.json").read_text(encoding="utf-8"))
    aliases = registry_aliases(registry)
    results: Dict[str, Dict[str, str]] = {}
    for company in sorted({v["company"] for v in approvals.values()}):
        evaluated = evaluate_all_questions(company, companies_root=companies_root)
        results[company] = {question: value.get("result") for question, value in evaluated["results"].items()}
    rows, tally = [], {}
    for key, approval in sorted(approvals.items()):
        company, question = approval["company"], approval["question"]
        if question in results.get(company, {}):
            result, how = results[company][question], "COVERED_DIRECT"
        elif aliases.get(question) in results.get(company, {}):
            result, how = results[company][aliases[question]], "COVERED_VIA_REGISTRY_ALIAS"
        else:
            result, how = None, "UNCOVERED"
        rows.append({"approval": key, "company": company, "question": question, "coverage": how, "evaluator_question": aliases.get(question) if how != "COVERED_DIRECT" else question, "result": result})
        tally[(how, result)] = tally.get((how, result), 0) + 1
    changed = [r for r in rows if r["result"] not in (None, "CLEAN")]
    return {"total_approvals": len(rows), "legacy_aliases_from_registry": aliases, "uncovered": [r["approval"] for r in rows if r["coverage"] == "UNCOVERED"],
            "changed_dependencies": len(changed), "tally": {f"{h}|{r}": n for (h, r), n in sorted(tally.items(), key=str)},
            "by_company_changed": {c: sum(1 for r in changed if r["company"] == c) for c in sorted({r["company"] for r in changed})}, "rows": rows}


if __name__ == "__main__":
    report = coverage(sys.argv[1])
    Path(sys.argv[2]).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=1))
