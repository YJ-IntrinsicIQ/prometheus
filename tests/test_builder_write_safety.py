"""P0 write safety: every company-intelligence builder needs an explicit absolute output root, refuses the served tree without authorization,
resolves its destinations before writing, can plan its outputs read-only, and cannot be redirected by the working directory or by a symlink.

Disposable fixtures only. The served companies/ tree is never an output root here; a stat-snapshot of it is compared before and after every run."""
import ast
import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from core import context_paths as cp  # noqa: E402

SERVED = cp.served_companies_root()


def served_snapshot():
    """(relative path, size, mtime_ns) of every file under the served tree: cheap and sufficient to prove nothing was created, changed or removed."""
    snap = []
    for dp, dn, fn in os.walk(SERVED):
        for f in fn:
            p = Path(dp) / f
            st = p.lstat()
            snap.append((str(p.relative_to(SERVED)), st.st_size, st.st_mtime_ns))
    return sorted(snap)


# ── builder specs: (id, prepare(root), plan(root, **auth), run(root, **auth), expected output file names) ──
def _year(root, company="acme", year="fy23"):
    d = root / company / year
    (d / "extracted").mkdir(parents=True, exist_ok=True)
    (d / "intelligence").mkdir(parents=True, exist_ok=True)
    (d / "extracted" / "clean_projects.json").write_text("[]")
    (d / "extracted" / "clean_capacity.json").write_text("[]")
    (d / "intelligence" / "company_intelligence.json").write_text(json.dumps({"management": {"summary": {}, "focus": {}, "credibility": {}}}))
    (d / "intelligence" / "management_summary.json").write_text(json.dumps({"company_management_actions": [], "company_results": [], "risk_responses": []}))
    return d


def _gold_memory(root, company="acme"):
    mem = root / company / "company_memory"
    for sub in ("gold", "management_progression", "financials", "projects", "capacity", "risks", "capital_allocation_outcomes"):
        (mem / sub).mkdir(parents=True, exist_ok=True)
    (mem / "management_progression" / "management_progression.json").write_text(json.dumps({"company": company, "progression_items": [], "events": []}))
    return mem


def _spec_projects():
    from intelligence.projects import ProjectsBuilder

    return ("projects", lambda r: _year(r), lambda r, **a: ProjectsBuilder("acme", r, **a).plan_outputs(), lambda r, **a: ProjectsBuilder("acme", r, **a).build(),
            {"projects_registry.json", "project_timelines.json", "project_assessments.json", "projects_validation.json", "projects_manifest.json"})


def _spec_capacity():
    from intelligence.capacity import CapacityEvolutionBuilder

    return ("capacity", lambda r: _year(r), lambda r, **a: CapacityEvolutionBuilder("acme", r, **a).plan_outputs(), lambda r, **a: CapacityEvolutionBuilder("acme", r, **a).build(),
            {"capacity_registry.json", "capacity_timelines.json", "capacity_assessments.json", "capacity_validation.json", "capacity_manifest.json"})


def _spec_capital_outcomes():
    from intelligence.capital_allocation_outcomes import CapitalAllocationOutcomesBuilder

    return ("capital_allocation_outcomes", lambda r: _gold_memory(r), lambda r, **a: CapitalAllocationOutcomesBuilder("acme", r, **a).plan_outputs(),
            lambda r, **a: CapitalAllocationOutcomesBuilder("acme", r, **a).build(),
            {"capital_allocation_outcomes.json", "capital_allocation_timelines.json", "capital_allocation_assessments.json", "capital_allocation_validation.json",
             "capital_allocation_manifest.json", "capital_allocation_longitudinal_profile.json"})


def _spec_longitudinal():
    from intelligence.capital_allocation_outcomes.longitudinal_profile import CapitalAllocationLongitudinalProfileBuilder

    return ("capital_allocation_longitudinal_profile", lambda r: _gold_memory(r), lambda r, **a: CapitalAllocationLongitudinalProfileBuilder("acme", r, **a).plan_outputs(),
            lambda r, **a: {"x": CapitalAllocationLongitudinalProfileBuilder("acme", r, **a).build()}, {"capital_allocation_longitudinal_profile.json"})


def _spec_commentary():
    from intelligence.management_commentary import ManagementCommentaryBuilder

    return ("management_commentary", lambda r: _year(r), lambda r, **a: ManagementCommentaryBuilder("acme", r, **a).plan_outputs(), lambda r, **a: ManagementCommentaryBuilder("acme", r, **a).build(),
            {"commentary_themes.json", "commentary_timelines.json", "commentary_assessments.json", "commentary_validation.json", "commentary_manifest.json"})


def _spec_quality():
    from intelligence.management_quality import ManagementQualityBuilder

    return ("management_quality", lambda r: _gold_memory(r), lambda r, **a: ManagementQualityBuilder("acme", r, **a).plan_outputs(), lambda r, **a: ManagementQualityBuilder("acme", r, **a).build(),
            {"management_quality_summary.json", "management_quality_dimensions.json", "management_quality_evidence.json", "management_quality_validation.json", "management_quality_manifest.json"})


def _spec_ask():
    from intelligence.ask_intrinsiciq.generator import generate_ask_intrinsiciq_view, plan_ask_intrinsiciq_outputs
    from intelligence.ask_intrinsiciq.paths import OUTPUT_FILE_NAMES

    return ("ask_intrinsiciq", lambda r: _gold_memory(r), lambda r, **a: plan_ask_intrinsiciq_outputs("acme", r, **a),
            lambda r, **a: {k: v for k, v in generate_ask_intrinsiciq_view("acme", r, force=True, **a).items() if k == "manifest"} and plan_ask_intrinsiciq_outputs("acme", r, **a),
            set(OUTPUT_FILE_NAMES.values()))


def _spec_risks():
    from intelligence.risks.builder import build_risk_evolution, plan_risk_evolution_outputs

    return ("risks", lambda r: _year(r), lambda r, **a: plan_risk_evolution_outputs("acme", r, **a), lambda r, **a: build_risk_evolution("acme", r, **a),
            {"risk_registry.json", "risk_timelines.json", "risk_assessments.json", "risk_validation.json", "risk_manifest.json"})


def _spec_economic():
    from intelligence.economic_attribution import runner

    def run(r, **a):
        runner.run("acme", r, **a)
        return runner.plan_outputs("acme", r, **a)

    def prep(r):
        mem = _gold_memory(r)
        (mem / "capital_allocation_outcomes" / "capital_allocation_outcomes.json").write_text(json.dumps({"allocations": []}))
        return mem

    return ("economic_attribution", prep, lambda r, **a: runner.plan_outputs("acme", r, **a), run, {"economic_attribution_intelligence.json", "economic_attribution_manifest.json"})


def _single(module, plan_name, write_name, filename, **extra):
    def spec():
        import importlib

        m = importlib.import_module(module)
        plan, write = getattr(m, plan_name), getattr(m, write_name)
        return (write_name, lambda r: _gold_memory(r), lambda r, **a: {filename: plan("acme", companies_root=r, **a) if extra.get("kw") else plan("acme", r, **a)},
                lambda r, **a: {filename: write("acme", companies_root=r, **a) if extra.get("kw") else write("acme", r, **a)}, {filename})
    return spec


def _spec_progression():
    from knowledge.management_progression.producer import plan_management_progression_outputs, write_management_progression

    return ("management_progression", lambda r: _gold_memory(r), lambda r, **a: plan_management_progression_outputs("acme", r, **a),
            lambda r, **a: write_management_progression("acme", companies_root=r, **a),
            {"management_progression.json", "management_progression_validation.json", "management_progression_manifest.json"})


def _spec_company_model():
    from knowledge.company_model.producer import plan_company_model_outputs, write_company_model

    return ("company_model", lambda r: _gold_memory(r), lambda r, **a: plan_company_model_outputs("acme", r, **a),
            lambda r, **a: write_company_model("acme", companies_root=r, **a), {"company_model.json", "company_model_validation.json", "company_model_manifest.json"})


SPECS = [
    _spec_projects, _spec_capacity, _spec_capital_outcomes, _spec_longitudinal, _spec_commentary, _spec_quality, _spec_ask, _spec_risks, _spec_economic,
    _single("intelligence.strategy_evolution.builder", "plan_strategy_evolution_timeline_output", "write_strategy_evolution_timeline", "strategy_evolution_timeline.json"),
    _single("intelligence.risk_evolution_timeline.builder", "plan_risk_evolution_timeline_output", "write_risk_evolution_timeline", "risk_evolution_timeline.json", kw=True),
    _single("intelligence.management_promises.builder", "plan_management_promise_tracker_output", "write_management_promise_tracker", "management_promise_tracker.json", kw=True),
    _single("intelligence.management_credibility.builder", "plan_management_credibility_synthesis_output", "write_management_credibility_synthesis", "management_credibility_synthesis.json"),
    _single("intelligence.capital_allocation.builder", "plan_capital_allocation_outcome_tracker_output", "write_capital_allocation_outcome_tracker", "capital_allocation_outcome_tracker.json", kw=True),
    _spec_progression, _spec_company_model,
]
IDS = ["projects", "capacity", "capital_allocation_outcomes", "longitudinal_profile", "management_commentary", "management_quality", "ask_intrinsiciq", "risks", "economic_attribution",
       "strategy_evolution", "risk_evolution_timeline", "management_promises", "management_credibility", "capital_allocation_tracker", "management_progression", "company_model"]


@pytest.fixture(params=SPECS, ids=IDS)
def spec(request):
    return request.param()


def names(planned):
    return {Path(p).name for p in planned.values()}


# ── the contract ──
def test_a_missing_output_root_is_rejected(spec):
    _, _, plan, run, _ = spec
    for bad in (None, ""):
        with pytest.raises(cp.WriteBoundaryError):
            plan(bad)
        with pytest.raises(cp.WriteBoundaryError):
            run(bad)


def test_omitting_the_root_is_a_type_error_there_is_no_default():
    from intelligence.projects import ProjectsBuilder, build_projects
    from intelligence.capacity import build_capacity_evolution

    with pytest.raises(TypeError):
        ProjectsBuilder(company="acme")
    with pytest.raises(TypeError):
        build_projects("acme")
    with pytest.raises(TypeError):
        build_capacity_evolution("acme")


def test_a_relative_root_is_rejected(spec):
    _, _, plan, run, _ = spec
    for bad in ("companies", Path("companies"), "relative/root", Path(".")):
        with pytest.raises(cp.WriteBoundaryError):
            plan(bad)
        with pytest.raises(cp.WriteBoundaryError):
            run(bad)


def test_the_served_tree_needs_explicit_authorization_and_nothing_is_written(spec):
    _, _, plan, run, _ = spec
    before = served_snapshot()
    for root in (SERVED, SERVED / "sun_pharma", REPO):
        with pytest.raises(cp.WriteBoundaryError):
            plan(root)
        with pytest.raises(cp.WriteBoundaryError):
            run(root)
    assert served_snapshot() == before


def test_plan_outputs_names_the_exact_destinations_and_creates_nothing(spec, tmp_path):
    _, prepare, plan, _, expected = spec
    root = tmp_path / "companies"
    prepare(root)
    before = sorted(str(p) for p in root.rglob("*"))
    planned = plan(root)
    assert names(planned) == expected
    for p in planned.values():
        assert Path(p).is_absolute() and (root.resolve() in Path(p).parents), p
    assert sorted(str(p) for p in root.rglob("*")) == before, "plan_outputs wrote something"


def test_a_scratch_root_run_writes_inside_the_root_and_leaves_the_served_tree_untouched(spec, tmp_path):
    _, prepare, plan, run, expected = spec
    root = tmp_path / "companies"
    prepare(root)
    before = served_snapshot()
    run(root)
    after = served_snapshot()
    assert after == before, "a scratch run changed the served tree"
    written = {p.name for p in root.rglob("*.json") if p.name in expected}
    assert written == expected, (expected - written)


def test_the_working_directory_cannot_redirect_the_output(spec, tmp_path, monkeypatch):
    _, prepare, plan, run, expected = spec
    root = tmp_path / "companies"
    prepare(root)
    monkeypatch.chdir(REPO)                                  # the served repo is the cwd: a cwd-relative default would land in companies/
    before = served_snapshot()
    run(root)
    assert served_snapshot() == before
    assert expected <= {p.name for p in root.rglob("*.json")}


def test_a_symlink_that_leaves_the_root_cannot_redirect_a_write(spec, tmp_path):
    _, prepare, plan, run, expected = spec
    root = tmp_path / "companies"
    prepare(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    memory = root / "acme" / "company_memory"
    memory.mkdir(parents=True, exist_ok=True)
    # replace every directory the builder may write into with a symlink to a directory outside the root
    for name in ("projects", "capacity", "capital_allocation_outcomes", "management_commentary", "management_quality", "ask_intrinsiciq", "risks", "economic_attribution", "gold",
                 "management_progression", "company_model"):
        target = memory / name
        if target.is_symlink():
            continue
        if target.exists():
            import shutil
            for child in target.iterdir():
                shutil.move(str(child), str(outside / child.name))
            target.rmdir()
        target.symlink_to(outside)
    preexisting = {p.name for p in outside.iterdir()}          # the fixture's own inputs moved there; only NEW files count as a leak
    with pytest.raises(cp.WriteBoundaryError):                 # the guard, not a crash elsewhere, must be what stops the write
        run(root)
    leaked = ({p.name for p in outside.iterdir()} - preexisting) & expected
    assert not leaked, f"a symlinked directory redirected a write outside the root: {leaked}"


def test_authorizing_the_served_tree_is_possible_only_with_the_explicit_flag(spec):
    """The flag opens the boundary check only; plan_outputs is read-only so this never writes."""
    _, _, plan, _, expected = spec
    before = served_snapshot()
    planned = plan(SERVED, authorize_served_write=True)
    assert names(planned) == expected and all(SERVED in Path(p).parents for p in planned.values())
    assert served_snapshot() == before


# ── no hard-coded or implicit destinations survive in the builders ──
HARDENED_MODULES = [
    "intelligence/projects/paths.py", "intelligence/capacity/paths.py", "intelligence/capital_allocation_outcomes/paths.py", "intelligence/economic_attribution/paths.py",
    "intelligence/management_commentary/paths.py", "intelligence/management_quality/paths.py", "intelligence/ask_intrinsiciq/paths.py",
    "intelligence/projects/builder.py", "intelligence/capacity/builder.py", "intelligence/capital_allocation_outcomes/builder.py",
    "intelligence/capital_allocation_outcomes/longitudinal_profile.py", "intelligence/management_commentary/builder.py", "intelligence/management_quality/builder.py",
    "intelligence/economic_attribution/runner.py", "intelligence/ask_intrinsiciq/generator.py", "intelligence/risks/builder.py", "intelligence/risks/writer.py",
    "intelligence/strategy_evolution/builder.py", "intelligence/risk_evolution_timeline/builder.py", "intelligence/management_promises/builder.py",
    "intelligence/management_credibility/builder.py", "intelligence/capital_allocation/builder.py", "knowledge/management_progression/producer.py", "knowledge/company_model/producer.py",
    "knowledge/company_memory/company_layer.py", "knowledge/company_memory/multi_year.py", "knowledge/company_memory/management_commitments.py", "knowledge/cim_contract.py",
    "knowledge/artifact_audit.py", "knowledge/quality_regression.py", "knowledge/financials/pcim_validation.py", "knowledge/financials/fundamentals_acceptance.py",
    "intelligence/management_promises/verification_bridge.py", "intelligence/regeneration_executor.py", "intelligence/investor_panel/runner.py",
    "intelligence/investor_panel/committee_synthesizer.py", "intelligence/investor_panel/briefs.py", "intelligence/investor_panel/committee_brief_qa.py",
    "intelligence/investor_panel/committee_brief_renderer.py",
]
WRITERS = ["intelligence/projects/writer.py", "intelligence/capacity/writer.py", "intelligence/capital_allocation_outcomes/writer.py", "intelligence/management_commentary/writer.py",
           "intelligence/management_quality/writer.py", "intelligence/ask_intrinsiciq/writer.py", "intelligence/risks/writer.py"]


@pytest.mark.parametrize("module", HARDENED_MODULES)
def test_no_builder_computes_a_destination_from_the_literal_companies_directory(module):
    """Path("companies") may appear only inside functions named logical_* (manifest labels, never I/O) and inside logical_company_path."""
    tree = ast.parse((REPO / module).read_text())
    offenders = []

    class V(ast.NodeVisitor):
        def __init__(self):
            self.stack = []

        def visit_FunctionDef(self, node):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, node):
            if isinstance(node.func, ast.Name) and node.func.id == "Path" and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == "companies":
                if not any(s.startswith("logical_") or s == "_logical_label" for s in self.stack):
                    offenders.append((node.lineno, "/".join(self.stack)))
            self.generic_visit(node)

    V().visit(tree)
    assert offenders == [], offenders


@pytest.mark.parametrize("module", WRITERS)
def test_shared_writers_write_only_through_the_guard(module):
    src = (REPO / module).read_text()
    tree = ast.parse(src)
    assert "guarded_write_text" in src
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("write_text", "mkdir", "replace", "rename"):
            pytest.fail(f"{module}:{node.lineno} performs a raw {node.func.attr}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
            pytest.fail(f"{module}:{node.lineno} opens a file directly")


def test_the_pipeline_gives_every_builder_an_explicit_root_and_never_swallows_a_refused_write():
    src = (REPO / "pipelines" / "run_company_pipeline.py").read_text()
    tree = ast.parse(src)
    guarded = {"ProjectsBuilder", "CapacityEvolutionBuilder", "CapitalAllocationOutcomesBuilder", "ManagementCommentaryBuilder", "ManagementQualityBuilder", "write_company_model",
               "write_management_progression", "write_management_promise_tracker", "write_management_credibility_synthesis", "write_capital_allocation_outcome_tracker",
               "write_strategy_evolution_timeline", "write_risk_evolution_timeline", "build_risk_evolution", "generate_ask_intrinsiciq_view", "_run_economic_attribution"}
    seen = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else None
            if name in guarded:
                seen.add(name)
                assert any(k.arg is None for k in node.keywords) or any(k.arg == "companies_root" for k in node.keywords), f"{name} at line {node.lineno} has no explicit root"
    assert seen == guarded, guarded - seen
    # a best-effort gold layer must re-raise a refused write instead of passing silently
    assert src.count("except WriteBoundaryError:") >= src.count("# Gold layer is best-effort")


# ── identities are stable when inputs are unchanged ──
def test_project_identities_are_stable_and_the_output_bytes_do_not_depend_on_the_root(tmp_path):
    from intelligence.projects import ProjectsBuilder
    import intelligence.projects.builder as pb

    items = [
        {"item_id": "p1", "project_name": "New manufacturing and integration facility", "description": "A new facility to support design, manufacturing, and integration of larger systems.",
         "location": "Chennai", "status": "Planned", "year": "2023", "confidence": "high"},
        {"item_id": "p2", "project_name": "Solar captive power plant", "description": "A captive solar power plant to cut energy cost.", "location": "Pune", "status": "Commissioned",
         "year": "2023", "confidence": "high"},
    ]

    def build(root):
        d = _year(root)
        (d / "extracted" / "clean_projects.json").write_text(json.dumps(items))
        original, pb._utc_now = pb._utc_now, (lambda: "2026-01-01T00:00:00Z")
        try:
            ProjectsBuilder("acme", root).build()
        finally:
            pb._utc_now = original
        out = root / "acme" / "company_memory" / "projects"
        return {f.name: f.read_bytes() for f in out.iterdir()}

    first = build(tmp_path / "a" / "companies")
    second = build(tmp_path / "b" / "deeper" / "companies")
    assert first == second, "bytes depend on the output root or on the run"
    registry = json.loads(first["projects_registry.json"])
    assert [p["project_id"] for p in registry["projects"]] == ["PJ-0001", "PJ-0002"]
    assert "tmp" not in first["projects_manifest.json"].decode() and "/private" not in first["projects_manifest.json"].decode()


# ── constructor contract for the remaining root-aware builders (company memory, CIM/PCIM, audit, investor panel) ──
def _ctor_specs():
    from intelligence.investor_panel.briefs import InvestorBriefBuilder
    from intelligence.investor_panel.committee_brief_qa import CommitteeBriefQAGate
    from intelligence.investor_panel.committee_brief_renderer import CommitteeBriefRenderer
    from intelligence.investor_panel.committee_synthesizer import InvestmentCommitteeSynthesizer
    from intelligence.investor_panel.runner import InvestorPanelRunner
    from knowledge.artifact_audit import ArtifactAudit
    from knowledge.cim_contract import CIMContractBuilder
    from knowledge.company_memory.company_layer import CompanyMemoryAggregateBuilder
    from knowledge.company_memory.management_commitments import ManagementCommitmentsBuilder
    from knowledge.company_memory.multi_year import MultiYearCompanyMemoryBuilder

    return {
        "company_memory_aggregate": lambda r, **a: CompanyMemoryAggregateBuilder("acme", r, **a),
        "multi_year": lambda r, **a: MultiYearCompanyMemoryBuilder("acme", r, **a),
        "management_commitments": lambda r, **a: ManagementCommitmentsBuilder("acme", r, **a),
        "cim_pcim": lambda r, **a: CIMContractBuilder("acme", r, **a),
        "artifact_audit": lambda r, **a: ArtifactAudit("acme", companies_root=r, **a),
        "investor_panel_runner": lambda r, **a: InvestorPanelRunner("acme", r, **a),
        "committee_synthesizer": lambda r, **a: InvestmentCommitteeSynthesizer("acme", r, **a),
        "investor_briefs": lambda r, **a: InvestorBriefBuilder("acme", r, **a),
        "committee_brief_renderer": lambda r, **a: CommitteeBriefRenderer("acme", r, **a),
        "committee_brief_qa": lambda r, **a: CommitteeBriefQAGate("acme", r, **a),
    }


CTOR_IDS = ["company_memory_aggregate", "multi_year", "management_commitments", "cim_pcim", "artifact_audit", "investor_panel_runner", "committee_synthesizer", "investor_briefs",
            "committee_brief_renderer", "committee_brief_qa"]


@pytest.fixture(params=CTOR_IDS)
def ctor(request, monkeypatch):
    # the panel runner builds an LLM client in its constructor: use the offline mock provider so no key or network is touched
    monkeypatch.setenv("PROMETHEUS_LLM_PROVIDER", "mock")
    return _ctor_specs()[request.param]


def test_ctor_rejects_missing_relative_and_served_roots(ctor):
    before = served_snapshot()
    for bad in (None, "", "companies", Path("companies"), "relative/root"):
        with pytest.raises(cp.WriteBoundaryError):
            ctor(bad)
    for root in (SERVED, SERVED / "sun_pharma", REPO):
        with pytest.raises(cp.WriteBoundaryError):
            ctor(root)
    assert served_snapshot() == before


def test_ctor_accepts_a_scratch_root_and_the_authorized_served_root_object_only_constructs(ctor, tmp_path):
    scratch = ctor(tmp_path / "companies")
    assert scratch.companies_root == (tmp_path / "companies").resolve()
    served = ctor(SERVED, authorize_served_write=True)          # constructing performs no write; the process-wide backstop still refuses one
    assert served.companies_root == SERVED


def test_the_process_wide_backstop_refuses_a_served_write_even_after_the_constructor_flag(tmp_path):
    from intelligence.projects import ProjectsBuilder

    builder = ProjectsBuilder("zz_probe_company", SERVED, authorize_served_write=True)
    before = served_snapshot()
    with pytest.raises(cp.WriteBoundaryError):
        builder.build()
    assert served_snapshot() == before and not (SERVED / "zz_probe_company").exists()


def test_the_backstop_refuses_raw_writes_into_the_served_tree_but_not_elsewhere(tmp_path):
    for op in (lambda: (SERVED / "_probe.txt").write_text("x"), lambda: (SERVED / "_probe_dir").mkdir(), lambda: os.replace(tmp_path / "a", SERVED / "_probe_b")):
        (tmp_path / "a").write_text("x")
        with pytest.raises(cp.WriteBoundaryError):
            op()
    assert not (SERVED / "_probe.txt").exists() and not (SERVED / "_probe_dir").exists()
    (tmp_path / "ok.txt").write_text("fine")                       # unrelated writes are untouched
    with cp.authorize_served_writes():
        assert cp.served_writes_authorized()
    assert not cp.served_writes_authorized()
