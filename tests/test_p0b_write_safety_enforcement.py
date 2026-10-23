"""P0-B: explicit company-data roots for CompanyContext, financial writers, ingestion processors and governance scripts."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from core import context_paths as cp
from core.company_context import CompanyContext, CompanyMemoryContext
from core.context_paths import WriteBoundaryError

REPO = Path(__file__).resolve().parents[1]
SERVED = REPO / "companies"
GOVERNANCE_SCRIPTS = ["m59_activate", "m59_4_close", "m59_2_trust_gate", "m59_question_batch", "answer_certification"]


def _digest(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()} if root.exists() else {}


# ── CompanyContext ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("bad", [None, "", "companies", "relative/dir"])
def test_company_context_rejects_missing_and_relative_roots(bad):
    with pytest.raises((WriteBoundaryError, TypeError)):
        CompanyContext("acme", "fy25", bad)


def test_company_context_rejects_the_served_tree_unless_authorized():
    with pytest.raises(WriteBoundaryError):
        CompanyContext("acme", "fy25", SERVED)
    assert CompanyContext("acme", "fy25", SERVED, authorize_served_write=True).companies_root == SERVED.resolve()


def test_company_context_is_independent_of_cwd_and_reads_where_it_writes(tmp_path, monkeypatch):
    scratch = tmp_path / "scratch"
    other = tmp_path / "elsewhere"; other.mkdir()
    (tmp_path / "companies").mkdir()          # a decoy relative companies/ must never be used
    for cwd in (tmp_path, other, REPO):
        monkeypatch.chdir(cwd)
        ctx = CompanyContext("acme", "fy25", scratch)
        assert ctx.company_root.is_absolute() and scratch.resolve() in ctx.company_root.parents
        assert ctx.logical(ctx.company_root / "x.json").startswith("companies/acme")


def test_company_memory_context_requires_a_root():
    with pytest.raises((WriteBoundaryError, TypeError)):
        CompanyMemoryContext("acme", None)


# ── environment variable alone never authorizes served writes ────────────────
def test_environment_variable_alone_does_not_authorize_served_writes(monkeypatch):
    monkeypatch.setenv("PROMETHEUS_AUTHORIZE_SERVED_WRITE", "1")
    assert cp.served_writes_authorized() is False
    with pytest.raises(WriteBoundaryError):
        cp.resolve_output_root(SERVED)
    with pytest.raises(WriteBoundaryError):
        (SERVED / "_p0b_probe.txt").write_text("x")
    assert not (SERVED / "_p0b_probe.txt").exists()


# ── financial writers ────────────────────────────────────────────────────────
def _shareholding_kwargs(tmp_path):
    n, r = tmp_path / "n.json", tmp_path / "r.json"
    n.write_text(json.dumps({"company": "acme", "year": "fy25", "fields": {}}))
    r.write_text(json.dumps({"tables": []}))
    return dict(company="acme", year="fy25", raw_tables_path=r, normalized_path=n, output_path=tmp_path / "out" / "shareholding_pattern.json")


@pytest.mark.parametrize("root", [None, "", "relative", SERVED])
def test_financial_writer_fails_closed_for_missing_relative_and_served_roots(tmp_path, root):
    from knowledge.financials.shareholding import write_shareholding_pattern
    before = _digest(SERVED / "tips") if (SERVED / "tips").exists() else {}
    with pytest.raises((WriteBoundaryError, TypeError)):
        write_shareholding_pattern(**_shareholding_kwargs(tmp_path), output_root=root)
    assert _digest(SERVED / "tips") == before and not (tmp_path / "out").exists()


def test_financial_writer_dry_run_writes_nothing_and_scratch_run_stays_inside(tmp_path):
    from knowledge.financials.shareholding import write_shareholding_pattern
    kw = _shareholding_kwargs(tmp_path)
    planned = write_shareholding_pattern(**kw, output_root=tmp_path, dry_run=True)
    assert not (tmp_path / "out").exists() and planned
    write_shareholding_pattern(**kw, output_root=tmp_path)
    assert (tmp_path / "out" / "shareholding_pattern.json").exists()


def test_financial_writer_refuses_a_destination_outside_the_root(tmp_path):
    from knowledge.financials.shareholding import write_shareholding_pattern
    kw = _shareholding_kwargs(tmp_path)
    root = tmp_path / "root"; root.mkdir()
    kw["output_path"] = tmp_path / "outside" / "shareholding_pattern.json"
    with pytest.raises(WriteBoundaryError):
        write_shareholding_pattern(**kw, output_root=root)
    assert not (tmp_path / "outside").exists()


# ── ingestion processors ─────────────────────────────────────────────────────
def test_ingestion_processors_fail_closed_without_a_root_and_for_served(tmp_path):
    from knowledge.document_processor import EarningsReleaseProcessor
    proc = EarningsReleaseProcessor()
    for root in (None, "relative", SERVED):
        with pytest.raises((WriteBoundaryError, TypeError)):
            proc.process(object(), tmp_path / "x.txt", companies_root=root)


# ── governance / certification scripts ───────────────────────────────────────
def test_certification_module_has_no_default_company_root():
    from pipelines import answer_certification as ac
    ac._COMPANIES_ROOT = None
    with pytest.raises(WriteBoundaryError):
        ac.companies_root()
    with pytest.raises(WriteBoundaryError):
        ac.configure_companies_root(SERVED)               # served tree needs the explicit flag
    with pytest.raises(WriteBoundaryError):
        ac.configure_companies_root("relative")


@pytest.mark.parametrize("script", GOVERNANCE_SCRIPTS)
def test_governance_script_requires_an_explicit_companies_root_and_changes_nothing(script):
    served = _digest(SERVED / "sun_pharma" / "company_memory" / "ask_intrinsiciq")
    registry = (REPO / "governance" / "approval_registry.json").read_bytes()
    args = [sys.executable, "-m", f"pipelines.{script}"] + (["--families", "all"] if script == "m59_activate" else [])
    env = {**os.environ, "PROMETHEUS_AUTHORIZE_SERVED_WRITE": "1"}   # the env var must not substitute for the flag
    r = subprocess.run(args, cwd=REPO, env=env, capture_output=True, text=True)
    assert r.returncode != 0 and "--companies-root" in (r.stderr + r.stdout)
    assert _digest(SERVED / "sun_pharma" / "company_memory" / "ask_intrinsiciq") == served
    assert (REPO / "governance" / "approval_registry.json").read_bytes() == registry


def test_governance_script_refuses_the_served_root_without_the_flag():
    r = subprocess.run([sys.executable, "-m", "pipelines.m59_activate", "--families", "all", "--apply", "--companies-root", str(SERVED)], cwd=REPO, capture_output=True, text=True)
    assert r.returncode != 0 and "served" in (r.stderr + r.stdout).lower()


def test_investor_acceptance_and_g4_validate_their_roots(tmp_path):
    from pipelines.run_investor_acceptance import run_acceptance
    with pytest.raises(WriteBoundaryError):
        run_acceptance("acme", [], tmp_path, companies_root="relative")
    with pytest.raises(WriteBoundaryError):
        run_acceptance("acme", [], SERVED / "_reports", companies_root=tmp_path)   # reports never go into the served tree


def test_pipeline_cli_scratch_dry_run_leaves_served_untouched(tmp_path):
    before = _digest(SERVED / "tips") if (SERVED / "tips").exists() else {}
    r = subprocess.run([sys.executable, "-c", "import pipelines.run_company_pipeline as p; print(p._pipeline_companies_root.__name__)"], cwd=tmp_path, env={**os.environ, "PYTHONPATH": f"{REPO}:{os.environ.get('PYTHONPATH','')}"}, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert _digest(SERVED / "tips") == before
