import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("approval_freshness_coverage", ROOT / "tools" / "approval_freshness_coverage.py")
A = importlib.util.module_from_spec(spec)
sys.modules["approval_freshness_coverage"] = A
spec.loader.exec_module(A)


def test_legacy_approved_ids_resolve_through_the_registrys_own_notes_not_invented_aliases():
    registry = json.loads((ROOT / "governance" / "answer_dependency_registry.json").read_text(encoding="utf-8"))
    assert A.registry_aliases(registry) == {"what-did-management-actually-deliver": "what-was-delivered-last-3-years", "what-could-go-wrong": "what-can-break-the-thesis"}


def test_every_approval_is_covered_by_the_evaluator_directly_or_through_a_registry_alias():
    report = A.coverage(str(ROOT / "companies"))          # read-only evaluation of the served tree
    assert report["total_approvals"] == 91 and report["uncovered"] == []
    assert sum(1 for r in report["rows"] if r["coverage"] == "COVERED_VIA_REGISTRY_ALIAS") == 8
