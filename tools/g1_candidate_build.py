"""M63/G1+G2 isolated candidate build. Re-runs the deterministic financial chain (normalize -> validate -> reconcile -> ratios ->
fact registry -> trends -> truth pack; capital ledger; and, for G2, the management-commitment register reclassified by the canonical
classifier -> progression -> promise tracker) with the CURRENT code into a scratch root. It copies only each company's financial JSONs,
never writes under companies/, and never touches approvals or served answers. No AI calls.

Usage: python3 -I tools/g1_candidate_build.py <out_root> [--years fy25,fy26] [--companies sun_pharma,tanla,ujjivan,datapatterns]
Output: <out_root>/companies/<company>/... plus <out_root>/candidate_summary.json (stored vs candidate key facts)."""
import json, shutil, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from knowledge.financials.normalizer import fill_missing_fields, normalize_financial_tables
from knowledge.financials.corporate_actions import write_corporate_actions
from knowledge.financials.discovery import write_financial_discovery
from knowledge.financials.basis_resolver import write_financial_basis_resolution
from knowledge.financials.financial_audit import write_financial_audit_report
from knowledge.financials.growth_calculator import write_financial_growth
from knowledge.financials.quality_summary import write_financial_quality_summary
from knowledge.financials.extractor import merge_raw_tables, write_financial_extraction
from knowledge.financials.statement_validator import write_financial_validation_report
from knowledge.financials.reconciler import write_financial_reconciliation_report
from knowledge.financials.ratio_calculator import write_financial_ratios
from knowledge.financials.fact_registry import write_financial_fact_registry
from knowledge.financials.registry_authority import settle_financial_authority
from knowledge.financials.authority_gate import bind_company
from knowledge.financials.trend_builder import write_financial_trends
from knowledge.financials.financial_memory_truth import build_financial_truth_pack
from knowledge.financials.investor_modules import write_investor_financial_modules
from knowledge.financials.memory_builder import write_financial_memory_artifacts
from intelligence.capital_allocation_outcomes.builder import build_capital_allocation_outcomes
from intelligence.economic_attribution.builder import build_economic_attribution_intelligence
from intelligence.management_promises.builder import build_management_promise_tracker
from knowledge.management_progression.producer import build_management_progression
from knowledge.company_memory import management_commitments as commitments_module
from scripts.pdf_reader import extract_pages
from scripts.smart_chunker import chunk_pages

DATA_PROCESSED = pathlib.Path(__file__).resolve().parents[1] / "data" / "Processed"

STALE_DERIVED = ("financial_validation_report.json", "financial_reconciliation_report.json", "financial_ratios.json", "financial_growth.json", "corporate_actions.json", "corporate_action_rejections.json",
                 "financial_fact_registry.json", "financial_truth_reconciliation_report.json", "financial_artifact_quarantine_report.json", "financial_basis_resolution.json",
                 "financial_quality_summary.json", "financial_audit_report.json", "_fact_registry_recon.json")
# Company-level financial-memory artifacts that the served tree also holds INSIDE some year folders (Sun Pharma fy23 / fy26): a second, stale copy of the company-level truth pack, trends and
# investor modules next to the year's own registry. They are not year-level artifacts; the candidate does not carry them (the migration tombstone manifest lists them) so that one company-
# level authority remains.
MISPLACED_COMPANY_LEVEL = ("financial_truth_pack.json", "financial_trends.json", "financial_memory_summary.json", "financial_memory_manifest.json", "financial_quality_evolution.json",
                           "financial_year_index.json", "investor_financial_modules_manifest.json", "ownership_evolution.json", "per_share_compounding_analysis.json",
                           "capital_allocation_roi_ledger.json", "capital_allocation_financial_timeline.json", "working_capital_quality_drilldown.json",
                           "order_revenue_cash_conversion_tracker.json", "owner_earnings_bridge.json", "financial_pcim_validation.json", "financial_quarantine_report.json",
                           "_fact_registry_recon.json")
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
    flags = ("--no-commitments", "--reextract", "--rechunk")
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
        for year_dir in dst.glob("fy*"):
            for name in MISPLACED_COMPANY_LEVEL:
                (year_dir / "financials" / name).unlink(missing_ok=True)
        for fy in years:
            fin = dst / fy / "financials"
            chunk_file = src / fy / "extracted" / "clean_chunks.json"
            rechunked = None
            if "--rechunk" in argv:
                # Primary-source extraction starts from the filing: stored chunks can pre-date the current chunker (a balance sheet's trade-payables row is missing from them). The chunks
                # are rebuilt from the annual-report PDF into the scratch tree and extracted SEPARATELY; their extra rows are merged into the baseline extraction (never replacing it).
                pdfs = sorted(DATA_PROCESSED.glob(f"{co}/{fy}/annual_report/*.pdf"), key=lambda f: ("afr" in f.name, f.name))
                reused = pathlib.Path(opt["--rechunked-from"]) / co / fy / "extracted" / "clean_chunks_rechunked.json" if opt.get("--rechunked-from") else None
                if pdfs:
                    rechunked = dst / fy / "extracted" / "clean_chunks_rechunked.json"
                    rechunked.parent.mkdir(parents=True, exist_ok=True)
                    if reused is not None and reused.exists():
                        shutil.copyfile(reused, rechunked)         # the chunker has not changed: the PDF text is not re-read (the chunks of an earlier build of the same filing are reused, byte for byte)
                    else:
                        chunk_pages(extract_pages(pdfs[0]), company=co, year=fy, document_type="annual_report", output_path=rechunked)
            if "--reextract" in argv and chunk_file.exists():
                # G3: the stored raw tables can pre-date the current extractor; re-run discovery + extraction from the stored chunks (no AI, scratch only)
                try:
                    write_financial_discovery(company=co, year=fy, chunk_path=chunk_file, output_path=fin / "financial_discovery.json", output_root=out)
                    write_financial_extraction(company=co, year=fy, chunk_path=chunk_file, discovery_path=fin / "financial_discovery.json", output_path=fin / "raw_financial_tables.json", output_root=out)
                except RuntimeError as exc:
                    not_regenerated.append(f"{co}:{fy}:extraction: {exc}")
            baseline_raw = (fin / "raw_financial_tables.json").read_text() if (fin / "raw_financial_tables.json").exists() else None
            if rechunked is not None:
                sup = out / "_supplement" / co / fy / "financials"
                try:
                    write_financial_discovery(company=co, year=fy, chunk_path=rechunked, output_path=sup / "financial_discovery.json", output_root=out)
                    write_financial_extraction(company=co, year=fy, chunk_path=rechunked, discovery_path=sup / "financial_discovery.json", output_path=sup / "raw_financial_tables.json", output_root=out)
                except RuntimeError as exc:
                    not_regenerated.append(f"{co}:{fy}:rechunked-extraction: {exc}")
                if (sup / "raw_financial_tables.json").exists() and baseline_raw is not None:
                    merged = merge_raw_tables(json.loads(baseline_raw), json.loads((sup / "raw_financial_tables.json").read_text()))
                    (fin / "raw_financial_tables.json").write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
            if baseline_raw is None and rechunked is not None and (out / "_supplement" / co / fy / "financials" / "raw_financial_tables.json").exists():
                shutil.copyfile(out / "_supplement" / co / fy / "financials" / "raw_financial_tables.json", fin / "raw_financial_tables.json")     # no baseline at all: the re-chunked extraction is all there is
            if not (fin / "raw_financial_tables.json").exists():
                continue
            # No stale carry-over: the copied served year contained every derived artifact of the OLD run. For a year that is rebuilt here, each of them is removed first, so a stage
            # that cannot run under the current code leaves the artifact ABSENT (and reported) instead of an old figure that disagrees with the rebuilt registry.
            for stale in STALE_DERIVED:
                (fin / stale).unlink(missing_ok=True)
            norm = None
            try:
                norm = normalize_financial_tables(company=co, year=fy, raw_tables_path=fin / "raw_financial_tables.json", allow_partial_balance_sheet=True)
                if baseline_raw is not None and rechunked is not None:
                    # strictly additive: the baseline extraction's figures stay; the re-chunked rows only fill fields the baseline lacks
                    base_path = out / "_supplement" / co / fy / "financials" / "raw_baseline.json"
                    base_path.parent.mkdir(parents=True, exist_ok=True)
                    base_path.write_text(baseline_raw, encoding="utf-8")
                    try:
                        norm = fill_missing_fields(normalize_financial_tables(company=co, year=fy, raw_tables_path=base_path, allow_partial_balance_sheet=True), norm)
                    except RuntimeError as exc:         # the baseline alone cannot be normalized (nothing to protect): the supplemented normalization stands
                        not_regenerated.append(f"{co}:{fy}:baseline-normalization: {exc}")
            except RuntimeError as exc:  # the current code cannot normalize this year: its stored normalized file is removed above and stays absent (reported)
                not_regenerated.append(f"{co}:{fy}:normalization: {exc}")
                (fin / "normalized_fundamentals.json").unlink(missing_ok=True)
                norm = None
            if norm is not None:
                (fin / "normalized_fundamentals.json").write_text(json.dumps(norm, indent=2, ensure_ascii=False), encoding="utf-8")
            for stage, call in (
                ("validation", lambda: write_financial_validation_report(company=co, year=fy, normalized_path=fin / "normalized_fundamentals.json", output_path=fin / "financial_validation_report.json", output_root=out)),
                ("reconciliation", lambda: write_financial_reconciliation_report(company=co, year=fy, normalized_path=fin / "normalized_fundamentals.json", output_path=fin / "financial_reconciliation_report.json", output_root=out)),
                # the registry decides which figures may be used; what it rejects leaves normalized_fundamentals.json before anything is derived from it
                ("authority", lambda: settle_financial_authority(company=co, year=fy, financial_root=fin, output_root=out, chunk_paths=[chunk_file])),
                ("validation", lambda: write_financial_validation_report(company=co, year=fy, normalized_path=fin / "normalized_fundamentals.json", output_path=fin / "financial_validation_report.json", output_root=out)),
                ("reconciliation", lambda: write_financial_reconciliation_report(company=co, year=fy, normalized_path=fin / "normalized_fundamentals.json", output_path=fin / "financial_reconciliation_report.json", output_root=out)),
                ("basis_resolution", lambda: write_financial_basis_resolution(company=co, year=fy, financial_root=fin, output_path=fin / "financial_basis_resolution.json", output_root=out)),
                ("ratios", lambda: write_financial_ratios(company=co, year=fy, normalized_path=fin / "normalized_fundamentals.json", reconciliation_path=fin / "financial_reconciliation_report.json", output_path=fin / "financial_ratios.json", output_root=out)),
                ("growth", lambda: write_financial_growth(company=co, year=fy, normalized_path=fin / "normalized_fundamentals.json", reconciliation_path=fin / "financial_reconciliation_report.json",
                                                          ratios_path=fin / "financial_ratios.json", output_path=fin / "financial_growth.json", output_root=out)),
                ("corporate_actions", lambda: write_corporate_actions(company=co, year=fy, normalized_path=fin / "normalized_fundamentals.json", raw_tables_path=fin / "raw_financial_tables.json",
                                                                      chunk_path=chunk_file if chunk_file.exists() else None,
                                                                      output_path=fin / "corporate_actions.json", output_root=out)),
                ("fact_registry", lambda: write_financial_fact_registry(company=co, year=fy, financial_root=fin, registry_output_path=fin / "financial_fact_registry.json",
                                                                         reconciliation_output_path=fin / "financial_truth_reconciliation_report.json", quarantine_output_path=fin / "financial_artifact_quarantine_report.json", output_root=out)),
                # shareholding_pattern.json is NOT rebuilt: nothing changed here touches ownership, and re-extracting it from the filing lost facts the served file carries
                ("audit", lambda: write_financial_audit_report(company=co, year=fy, financials_dir=fin, output_path=fin / "financial_audit_report.json", output_root=out)),
                ("quality_summary", lambda: write_financial_quality_summary(company=co, financial_root=fin, year=fy, output_path=fin / "financial_quality_summary.json", output_root=out)),
            ):
                try:
                    call()
                except (RuntimeError, ValueError, FileNotFoundError) as exc:  # the stage cannot run under the current code: its artifact stays absent and is reported
                    not_regenerated.append(f"{co}:{fy}:{stage}: {exc}")
        write_financial_trends(company=co, company_root=dst, output_path=dst / "company_memory" / "financials" / "financial_trends.json", output_root=out)
        pack = build_financial_truth_pack(company=co, company_root=dst)
        (dst / "company_memory" / "financials" / "financial_truth_pack.json").write_text(json.dumps(pack, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        # Phase 1: everything that is derived from the registry is rebuilt from the candidate registry (never left as the served copy): the financial memory set
        # (year index, quality evolution, capital-allocation financial timeline, ownership, summary, manifest, truth pack) and the investor modules (ROI ledger, owner earnings, ...).
        try:
            write_financial_memory_artifacts(company=co, company_root=dst, output_dir=dst / "company_memory" / "financials", output_root=out)
            write_investor_financial_modules(company=co, company_root=dst, output_dir=dst / "company_memory" / "financials" / "investor_financial_modules", output_root=out)
            pack = json.loads((dst / "company_memory" / "financials" / "financial_truth_pack.json").read_text(encoding="utf-8"))
        except (RuntimeError, ValueError) as exc:     # a company whose years cannot all be rebuilt keeps its served artifact for that stage, and says so
            not_regenerated.append(f"{co}:financial_memory/investor_modules: {exc}")
            # the copied served financial memory describes the OLD extraction: it is removed, not shipped as if it were the candidate's (the company then has year-level facts only)
            memory_dir = dst / "company_memory" / "financials"
            for stale in list(memory_dir.glob("*.json")) + list((memory_dir / "investor_financial_modules").glob("*.json")):
                stale.unlink()
            not_regenerated.append(f"{co}:financial_memory: stale served company-level financial memory removed from the candidate")
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
            elif entry.name == "company_memory":          # served memory, except the financial set the candidate rebuilt above
                (ledger_root / "company_memory").mkdir()
                for sub in entry.iterdir():
                    (ledger_root / "company_memory" / sub.name).symlink_to(dst / "company_memory" / "financials" if sub.name == "financials" else sub)
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
        bind_company(dst, output_root=out)       # every financial-derived artifact is recorded against the registries that now exist (the last step of a build)
        stored = json.loads((src / "company_memory" / "financials" / "financial_truth_pack.json").read_text())
        before, after = facts(stored), facts(pack)
        summary[co] = {f"{m}:{fy}": {"stored": before.get(k), "candidate": after.get(k)} for k in sorted(set(before) | set(after)) for m, fy in [k] if before.get(k) != after.get(k)}
    summary["_not_regenerated"] = not_regenerated
    (out / "candidate_summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=1, default=str))


if __name__ == "__main__":
    main(sys.argv[1:])
