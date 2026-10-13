"""M63/G1+G2 isolated candidate build. Re-runs the deterministic financial chain (normalize -> validate -> reconcile -> ratios ->
fact registry -> trends -> truth pack; capital ledger; and, for G2, the management-commitment register reclassified by the canonical
classifier -> progression -> promise tracker) with the CURRENT code into a scratch root. It copies only each company's financial JSONs,
never writes under companies/, and never touches approvals or served answers. No AI calls.

Usage: python3 -I tools/g1_candidate_build.py <out_root> [--years fy25,fy26] [--companies sun_pharma,tanla,ujjivan,datapatterns]
Output: <out_root>/companies/<company>/... plus <out_root>/candidate_summary.json (stored vs candidate key facts)."""
import json, shutil, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from knowledge.financials.normalizer import normalize_financial_tables
from knowledge.financials.corporate_actions import write_corporate_actions
from knowledge.financials.discovery import write_financial_discovery
from knowledge.financials.extractor import write_financial_extraction
from knowledge.financials.statement_validator import write_financial_validation_report
from knowledge.financials.reconciler import write_financial_reconciliation_report
from knowledge.financials.ratio_calculator import write_financial_ratios
from knowledge.financials.fact_registry import write_financial_fact_registry
from knowledge.financials.trend_builder import write_financial_trends
from knowledge.financials.financial_memory_truth import build_financial_truth_pack
from intelligence.capital_allocation_outcomes.builder import build_capital_allocation_outcomes
from intelligence.economic_attribution.builder import build_economic_attribution_intelligence
from intelligence.management_promises.builder import build_management_promise_tracker
from knowledge.management_progression.producer import build_management_progression
from knowledge.company_memory import management_commitments as commitments_module

KEYS = ("cash_and_equivalents", "total_debt", "net_debt", "capex", "cfo", "revenue", "pat")


def facts(pack):
    """{(metric, fy): (value, source_line_item, period)} for the key metrics in a truth pack's usable lists."""
    out = {}
    for lst in ("usable_current_metrics", "usable_derived_metrics", "partial_metrics"):
        for f in pack.get(lst, []):
            if f.get("metric_id") in KEYS and f.get("fiscal_year"):
                out.setdefault((f["metric_id"], f["fiscal_year"]), (f.get("value"), f.get("source_line_item"), f.get("period")))
    return out


def commitments_stage(co: str, src: pathlib.Path, dst: pathlib.Path, out: pathlib.Path) -> None:
    """Apply the canonical commitment classifier to the stored register (identity = fingerprint is untouched), then rebuild progression and
    the promise tracker from it. The register's own gating (statement type/actor) is approximated from the stored fields."""
    memory_src, memory_dst = src / "company_memory", dst / "company_memory"
    for name in ("management_commitments", "management_progression", "gold"):
        shutil.copytree(memory_src / name, memory_dst / name, dirs_exist_ok=True)
    register_path = memory_dst / "management_commitments" / "management_commitments.json"
    register = json.loads(register_path.read_text())
    # G2.1/B1: the builder quarantines a statement whose source sentence gives it to someone else (or leaves attribution unclear). The stored register
    # predates that gate, so apply it here the same way (ids of the remaining commitments are NOT renumbered in this approximation; a real rebuild renumbers).
    context = {fy.name: commitments_module.ManagementCommitmentsBuilder._load_promise_context(fy) for fy in sorted(src.glob("fy*"))}
    kept = []
    for c in register["commitments"]:
        ref = (c.get("source_references") or [{}])[0]
        verdict = commitments_module.attribute_statement(c["original_statement"], context.get(str(ref.get("period")), {}).get((commitments_module._normalize_text(c["original_statement"]), ref.get("page")), ""))
        if verdict["attribution"] == "THIRD_PARTY" or (verdict["attribution"] == "UNCLEAR" and not verdict["basis"].startswith("no_")):
            register.setdefault("quarantined_candidates", []).append({"period": ref.get("period"), "source_artifact": ref.get("source_artifact"), "source_item_id": ref.get("source_item_id"), "original_statement": c["original_statement"],
                                                                      "actor_type": verdict["actor_type"] or "unknown", "quarantine_reason": "EXTERNAL_ACTOR" if verdict["attribution"] == "THIRD_PARTY" else "UNCLASSIFIED_STATEMENT",
                                                                      "attribution": verdict})
        else:
            c["_source_intent"] = False if (verdict["basis"] == "no_forward_verb_in_sentence" and not verdict.get("intent_in_source")) else None   # outlook, not an intent verb
            kept.append(c)
    register["commitments"], register["commitment_count"] = kept, len(kept)
    register["quarantined_candidate_count"] = len(register.get("quarantined_candidates", []))
    for c in register["commitments"]:
        eligible = c.get("actor_type") in commitments_module.COMPANY_ACTORS and (c.get("statement_type") in commitments_module.ELIGIBLE_COMMITMENT_STATEMENTS or c.get("accountability_ontology") == "VERIFIABLE_COMMITMENT")
        source_intent = c.pop("_source_intent", None)
        c["accountability_ontology"] = commitments_module.classify_accountability_ontology(c["original_statement"], commitment_eligible=eligible, source_intent=source_intent)
        c["verification_applicability"] = "APPLICABLE" if c["accountability_ontology"] == "VERIFIABLE_COMMITMENT" else "NOT_APPLICABLE"
        c.update(commitments_module.canonical_commitment_fields(original_statement=c["original_statement"], normalized_commitment=c["normalized_commitment"],
                                                                 expected_timeframe=c["expected_timeframe"], announcement_period=c["announcement_period"], ontology=c["accountability_ontology"], source_intent=source_intent))
    register_path.write_text(json.dumps(register, indent=2, ensure_ascii=False), encoding="utf-8")
    # a scratch companies_root: read-only inputs link to the served tree, the three rebuilt directories are the candidate copies
    cr = out / "cr" / co
    (cr / "company_memory").mkdir(parents=True, exist_ok=True)
    for entry in src.iterdir():
        if entry.name != "company_memory" and not (cr / entry.name).exists():
            (cr / entry.name).symlink_to(entry)
    for entry in memory_src.iterdir():
        target = cr / "company_memory" / entry.name
        if not target.exists():
            target.symlink_to(memory_dst / entry.name if entry.name in ("management_commitments", "management_progression", "gold") else entry)
    progression = build_management_progression(co, companies_root=out / "cr")
    (memory_dst / "management_progression" / "management_progression.json").write_text(json.dumps(progression, indent=2, ensure_ascii=False), encoding="utf-8")
    tracker = build_management_promise_tracker(co, companies_root=out / "cr")
    (memory_dst / "gold" / "management_promise_tracker.json").write_text(json.dumps(tracker, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def main(argv):
    out = pathlib.Path(argv[0]).resolve()
    flags = ("--no-commitments", "--reextract")
    opt = dict(zip([a for a in argv[1:] if a not in flags][0::2], [a for a in argv[1:] if a not in flags][1::2]))
    years = opt.get("--years", "fy25,fy26").split(",")
    companies = opt.get("--companies", "sun_pharma,tanla,ujjivan,datapatterns").split(",")
    if str(out).startswith(str(ROOT / "companies")):
        raise SystemExit("refusing to write under companies/")
    summary, not_regenerated = {}, []
    for co in companies:
        src, dst = ROOT / "companies" / co, out / "companies" / co
        for d in list(src.glob("fy*/financials")) + list(src.glob("fy*/intelligence")) + [src / "company_memory" / "financials"]:  # intelligence/: year-eligibility inputs only
            shutil.copytree(d, dst / d.relative_to(src), dirs_exist_ok=True)
        for fy in years:
            fin = dst / fy / "financials"
            chunk_file = src / fy / "extracted" / "clean_chunks.json"
            if "--reextract" in argv and chunk_file.exists():
                # G3: the stored raw tables can pre-date the current extractor; re-run discovery + extraction from the stored chunks (no AI, scratch only)
                try:
                    write_financial_discovery(company=co, year=fy, chunk_path=chunk_file, output_path=fin / "financial_discovery.json")
                    write_financial_extraction(company=co, year=fy, chunk_path=chunk_file, discovery_path=fin / "financial_discovery.json", output_path=fin / "raw_financial_tables.json")
                except RuntimeError as exc:
                    not_regenerated.append(f"{co}:{fy}:extraction: {exc}")
            if not (fin / "raw_financial_tables.json").exists():
                continue
            try:
                norm = normalize_financial_tables(company=co, year=fy, raw_tables_path=fin / "raw_financial_tables.json")
            except RuntimeError as exc:  # current code cannot rebuild this year (pre-existing): keep the stored normalized file, still run downstream
                not_regenerated.append(f"{co}:{fy}: {exc}")
                norm = None
            if norm is not None:
                (fin / "normalized_fundamentals.json").write_text(json.dumps(norm, indent=2, ensure_ascii=False), encoding="utf-8")
            for stage, call in (
                ("validation", lambda: write_financial_validation_report(company=co, year=fy, normalized_path=fin / "normalized_fundamentals.json", output_path=fin / "financial_validation_report.json")),
                ("reconciliation", lambda: write_financial_reconciliation_report(company=co, year=fy, normalized_path=fin / "normalized_fundamentals.json", output_path=fin / "financial_reconciliation_report.json")),
                ("ratios", lambda: write_financial_ratios(company=co, year=fy, normalized_path=fin / "normalized_fundamentals.json", reconciliation_path=fin / "financial_reconciliation_report.json", output_path=fin / "financial_ratios.json")),
                ("corporate_actions", lambda: write_corporate_actions(company=co, year=fy, normalized_path=fin / "normalized_fundamentals.json", raw_tables_path=fin / "raw_financial_tables.json",
                                                                      chunk_path=chunk_file if chunk_file.exists() else None,
                                                                      output_path=fin / "corporate_actions.json")),
                ("fact_registry", lambda: write_financial_fact_registry(company=co, year=fy, financial_root=fin, registry_output_path=fin / "financial_fact_registry.json",
                                                                         reconciliation_output_path=fin / "financial_truth_reconciliation_report.json", quarantine_output_path=fin / "financial_artifact_quarantine_report.json")),
            ):
                try:
                    call()
                except RuntimeError as exc:  # stage cannot run under current code (pre-existing): keep the stored artifact for it and say so
                    not_regenerated.append(f"{co}:{fy}:{stage}: {exc}")
        write_financial_trends(company=co, company_root=dst, output_path=dst / "company_memory" / "financials" / "financial_trends.json")
        pack = build_financial_truth_pack(company=co, company_root=dst)
        (dst / "company_memory" / "financials" / "financial_truth_pack.json").write_text(json.dumps(pack, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        # Capital ledger + economic attribution (the cases the Story/Discoveries/Question pages read). Inputs are read from the served tree.
        cao_dir = dst / "company_memory" / "capital_allocation_outcomes"
        cao_dir.mkdir(parents=True, exist_ok=True)
        ledger_root = out / "ledger_root" / co                      # served tree, except that each year's financials are the candidate's (corporate actions carry the buyback disclosure)
        if ledger_root.exists():
            shutil.rmtree(ledger_root)
        ledger_root.mkdir(parents=True)
        for entry in src.iterdir():
            if entry.name.startswith("fy") and (dst / entry.name / "financials").exists():
                (ledger_root / entry.name).mkdir()
                for sub in entry.iterdir():
                    (ledger_root / entry.name / sub.name).symlink_to(dst / entry.name / "financials" if sub.name == "financials" else sub)
            else:
                (ledger_root / entry.name).symlink_to(entry)
        for filename, payload in build_capital_allocation_outcomes(company=co, company_root=ledger_root).items():
            (cao_dir / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        mem = src / "company_memory"
        econ = build_economic_attribution_intelligence(cao_dir / "capital_allocation_outcomes.json", mem / "management_progression" / "management_progression.json",
                                                       mem / "gold" / "risk_evolution_timeline.json", mem / "financial_truth_pack.json")
        (dst / "company_memory" / "economic_attribution").mkdir(parents=True, exist_ok=True)
        (dst / "company_memory" / "economic_attribution" / "economic_attribution_intelligence.json").write_text(json.dumps(econ, indent=2, ensure_ascii=False), encoding="utf-8")
        if "--no-commitments" not in argv:
            commitments_stage(co, src, dst, out)
        stored = json.loads((src / "company_memory" / "financials" / "financial_truth_pack.json").read_text())
        before, after = facts(stored), facts(pack)
        summary[co] = {f"{m}:{fy}": {"stored": before.get(k), "candidate": after.get(k)} for k in sorted(set(before) | set(after)) for m, fy in [k] if before.get(k) != after.get(k)}
    summary["_not_regenerated"] = not_regenerated
    (out / "candidate_summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=1, default=str))


if __name__ == "__main__":
    main(sys.argv[1:])
