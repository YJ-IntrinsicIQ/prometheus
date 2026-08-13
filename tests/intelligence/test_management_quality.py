import json
from pathlib import Path

from intelligence.management_quality import ManagementQualityBuilder, validate_management_quality_payload
from intelligence.management_quality.evidence_linker import build_management_quality_evidence
from intelligence.management_quality.synthesis import evaluate_dimensions


def _mkdirs(base_dir: Path, company: str) -> dict[str, Path]:
    root = base_dir / "companies" / company / "company_memory"
    financial_dir = root / "financials"
    investor_dir = root / "investor_panel"
    projects_dir = root / "projects"
    capacity_dir = root / "capacity"
    commitments_dir = root / "management_commitments"
    commentary_dir = root / "management_commentary"
    capital_dir = root / "capital_allocation_outcomes"
    risks_dir = root / "risks"
    for path in (financial_dir / "investor_financial_modules", investor_dir, projects_dir, capacity_dir, commitments_dir, commentary_dir, capital_dir, risks_dir):
        path.mkdir(parents=True, exist_ok=True)
    return {
        "root": root,
        "financial": financial_dir,
        "investor": investor_dir,
        "projects": projects_dir,
        "capacity": capacity_dir,
        "commitments": commitments_dir,
        "commentary": commentary_dir,
        "capital": capital_dir,
        "risks": risks_dir,
    }


def _write_json(path: Path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_positive_fixture(base_dir: Path, company: str):
    paths = _mkdirs(base_dir, company)
    financial_dir = paths["financial"]
    investor_dir = paths["investor"]

    _write_json(
        paths["commitments"] / "management_commitments.json",
        {
            "company": company,
            "commitment_count": 1,
            "commitments": [
                {
                    "id": "MC-1",
                    "topic": "Capacity expansion",
                    "category": "Capacity",
                    "announcement_period": "fy23",
                    "original_statement": "We will expand capacity.",
                    "normalized_commitment": "Expand capacity.",
                    "expected_timeframe": "fy24",
                    "priority": "high",
                    "status": "Delivered",
                    "supporting_evidence": "Plant commissioned.",
                    "delivery_assessment": "Delivered.",
                    "confidence": {"level": "high", "basis": ["annual report"], "limitations": []},
                    "investor_implication": "Execution appears on schedule.",
                    "source_references": [{"source_artifact": "management_summary.json", "source_item_id": "m1", "period": "fy23"}],
                    "progression": {"turning_points": [{"event_id": "tp-1"}]},
                    "progression_validation": {"status": "pass", "issue_count": 0, "issues": []},
                }
            ],
        },
    )
    _write_json(
        paths["projects"] / "projects_registry.json",
        {
            "company": company,
            "project_count": 1,
            "projects": [
                {
                    "project_id": "PJ-1",
                    "project_name": "New plant",
                    "normalized_name": "New plant",
                    "project_type": "facility",
                    "objective": "Expand production",
                    "business_rationale": "Support growth",
                    "current_status": "operational",
                    "announcement_period": "fy23",
                    "latest_period": "fy24",
                    "confidence": {"level": "high", "basis": ["project update"], "limitations": []},
                    "source_references": [{"source_artifact": "clean_projects.json", "source_item_id": "p1", "period": "fy23"}],
                    "progression": {"turning_points": [{"event_id": "tp-2"}]},
                }
            ],
        },
    )
    _write_json(
        paths["projects"] / "project_assessments.json",
        {
            "company": company,
            "assessments": [
                {
                    "project_id": "PJ-1",
                    "project_name": "New plant",
                    "execution_status": "operational",
                    "economic_impact_status": "early_evidence",
                    "execution_summary": "Plant commissioned and operational.",
                    "observed_business_effect": "Execution progressed.",
                    "observed_financial_effect": "Effect remains early.",
                    "what_changed": "Commissioned.",
                    "why_it_changed": "Construction completed.",
                    "unresolved_questions": [],
                    "conviction_impact": "strengthened",
                    "evidence_periods": ["fy23", "fy24"],
                    "confidence": {"level": "high", "basis": ["operational evidence"], "limitations": []},
                }
            ],
        },
    )
    _write_json(
        paths["capacity"] / "capacity_registry.json",
        {
            "company": company,
            "capacity_count": 1,
            "capacity_items": [
                {
                    "capacity_id": "CP-1",
                    "capacity_name": "New plant capacity",
                    "normalized_name": "New plant capacity",
                    "capacity_type": "manufacturing",
                    "purpose": "Expand production",
                    "current_status": "operational",
                    "utilization_status": "materially_utilized",
                    "latest_period": "fy24",
                    "announcement_period": "fy23",
                    "confidence": {"level": "high", "basis": ["capacity note"], "limitations": []},
                    "source_references": [{"source_artifact": "clean_capacity.json", "source_item_id": "c1", "period": "fy23"}],
                    "progression_summary": {"what_changed": "The plant became operational.", "why_it_changed": "Construction finished."},
                    "capacity_assessment": {
                        "execution_status": "operational",
                        "economic_impact_status": "early_evidence",
                        "observed_business_effect": "Capacity is visible.",
                        "observed_financial_effect": "Noisy but positive.",
                        "utilization_status": "materially_utilized",
                        "confidence": {"level": "high", "basis": ["operational evidence"], "limitations": []},
                        "evidence_periods": ["fy23", "fy24"],
                        "unresolved_questions": [],
                    },
                    "utilization_assessment": {
                        "utilization_status": "materially_utilized",
                        "confidence": {"level": "high", "basis": ["utilization"], "limitations": []},
                    },
                    "unresolved_questions": [],
                }
            ],
        },
    )
    _write_json(
        paths["risks"] / "risk_registry.json",
        {
            "company": company,
            "risk_count": 2,
            "risks": [
                {
                    "risk_id": "R-1",
                    "risk_name": "Customer concentration",
                    "normalized_name": "customer concentration",
                    "risk_category": "customer",
                    "current_status": "mitigated",
                    "first_observed_period": "fy23",
                    "latest_period": "fy24",
                    "materiality": {"level": "medium"},
                    "mitigations": [{"mitigation_action": "Diversify customer base"}],
                    "confidence": {"level": "medium", "basis": ["risk disclosure"], "limitations": []},
                    "source_references": [{"source_artifact": "management_summary.json", "source_item_id": "r1", "period": "fy23"}],
                }
                ,
                {
                    "risk_id": "R-2",
                    "risk_name": "Input cost pressure",
                    "normalized_name": "input cost pressure",
                    "risk_category": "financial",
                    "current_status": "persistent",
                    "first_observed_period": "fy23",
                    "latest_period": "fy24",
                    "materiality": {"level": "medium"},
                    "mitigations": [],
                    "confidence": {"level": "medium", "basis": ["risk disclosure"], "limitations": []},
                    "source_references": [{"source_artifact": "management_summary.json", "source_item_id": "r2", "period": "fy24"}],
                },
            ],
        },
    )
    _write_json(
        paths["commentary"] / "commentary_themes.json",
        {
            "company": company,
            "commentary_count": 1,
            "themes": [
                {
                    "theme_id": "CT-1",
                    "theme_name": "Execution",
                    "normalized_theme": "execution",
                    "theme_category": "execution",
                    "current_position": "strengthened",
                    "first_observed_period": "fy23",
                    "latest_period": "fy24",
                    "current_emphasis": "Management now emphasizes delivery.",
                    "consistency_assessment": {"consistency_status": "aligned", "basis": ["annual report"], "limitations": []},
                    "evidence_alignment": {"alignment_status": "aligned", "basis": ["project completion"], "limitations": []},
                    "confidence": {"level": "high", "basis": ["commentary"], "limitations": []},
                    "source_references": [{"source_artifact": "management_summary.json", "source_item_id": "ct1", "period": "fy23"}],
                    "progression_summary": {"what_changed": "The message became more execution-oriented.", "why_it_changed": "Delivery evidence improved."},
                }
            ],
        },
    )
    _write_json(
        paths["capital"] / "capital_allocation_outcomes.json",
        {
            "company": company,
            "allocation_count": 1,
            "allocations": [
                {
                    "allocation_id": "CAO-1",
                    "allocation_name": "Capacity expansion",
                    "allocation_category": "capacity_expansion",
                    "normalized_name": "Capacity expansion",
                    "outcome_status": "clearly_observed",
                    "operating_outcome": "Plant commissioned.",
                    "financial_outcome": "Returns are beginning to show.",
                    "per_share_outcome": "Per-share economics look better.",
                    "return_evidence": [{"period": "fy24", "kind": "project", "note": "Commissioned plant"}],
                    "confidence": {"level": "high", "basis": ["capital timeline"], "limitations": []},
                    "source_references": [{"source_artifact": "capital_allocation_financial_timeline.json", "source_item_id": "ca1", "period": "fy24"}],
                    "progression_summary": {"what_changed": "Payoff became visible.", "why_it_changed": "The plant went live."},
                    "current_status": "deployed",
                }
            ],
        },
    )
    _write_json(
        financial_dir / "financial_truth_pack.json",
        {
            "company": company,
            "generated_at": "2026-08-08T00:00:00Z",
            "years_covered": ["fy23", "fy24"],
            "financial_panel_status": "usable",
            "financial_panel_status_reason": "Financial evidence is usable.",
        },
    )
    _write_json(
        financial_dir / "investor_financial_modules" / "owner_earnings_bridge.json",
        {
            "company": company,
            "generated_at": "2026-08-08T00:00:00Z",
            "years_covered": ["fy23", "fy24"],
            "bridges": [
                {
                    "fiscal_year": "fy23",
                    "owner_earnings_estimate": 12.0,
                    "conservative_fcf_after_total_capex": 10.0,
                    "owner_earnings_precision_status": "usable",
                    "maintenance_growth_split_status": "usable",
                },
                {
                    "fiscal_year": "fy24",
                    "owner_earnings_estimate": 18.0,
                    "conservative_fcf_after_total_capex": 15.0,
                    "owner_earnings_precision_status": "usable",
                    "maintenance_growth_split_status": "usable",
                },
            ],
            "warnings": [],
            "limitations": [],
        },
    )
    _write_json(
        financial_dir / "investor_financial_modules" / "per_share_compounding_analysis.json",
        {
            "company": company,
            "generated_at": "2026-08-08T00:00:00Z",
            "years_covered": ["fy23", "fy24"],
            "analysis": [
                {
                    "fiscal_year": "fy23",
                    "closing_shares": 100.0,
                    "eps_basic": 1.0,
                    "per_share_compounding_status": "usable",
                    "dilution_status": "none",
                    "fcf_per_share_confidence": "usable",
                },
                {
                    "fiscal_year": "fy24",
                    "closing_shares": 90.0,
                    "eps_basic": 1.5,
                    "per_share_compounding_status": "usable",
                    "dilution_status": "none",
                    "fcf_per_share_confidence": "usable",
                },
            ],
            "warnings": [],
            "limitations": [],
        },
    )
    _write_json(
        paths["investor"] / "committee_synthesis.json",
        {
            "company": company,
            "analysis_mode": "committee_synthesis_v1",
            "analysts_considered": ["graham", "buffett"],
            "missing_analysts": [],
            "excluded_analysts": [],
            "years_considered": ["fy23", "fy24"],
            "overall_committee_view": {"summary": "Management appears broadly disciplined.", "confidence": "medium", "dominant_tension": "capital allocation", "rating": "reasonably_strong"},
            "financial_committee_view": {"financial_consensus": "Positive", "financial_red_flags": [], "financial_strengths": [], "financial_concerns": []},
            "areas_of_agreement": [],
            "areas_of_disagreement": [],
            "strongest_positive_signals": [],
            "most_important_risks": [],
            "critical_unknowns": [],
            "investigation_questions": [],
            "evidence_ids": [],
            "evidence_quality_notes": [],
            "synthesis_limits": [],
            "generated_at": "2026-08-08T00:00:00Z",
            "evidence_id_normalization": [],
            "analyst_coverage_map": {},
            "financial_warning_manifest": [],
            "committee_financial_truth": {},
            "blocked_financial_warning_manifest": [],
            "executive_committee_summary": "Management looks mostly consistent.",
            "synthesis_narrative": "Management quality looks reasonably strong.",
        },
    )


def _load_outputs(base_dir: Path, company: str):
    output_dir = base_dir / "companies" / company / "company_memory" / "management_quality"
    summary = json.loads((output_dir / "management_quality_summary.json").read_text(encoding="utf-8"))
    dimensions = json.loads((output_dir / "management_quality_dimensions.json").read_text(encoding="utf-8"))
    evidence = json.loads((output_dir / "management_quality_evidence.json").read_text(encoding="utf-8"))
    validation = json.loads((output_dir / "management_quality_validation.json").read_text(encoding="utf-8"))
    manifest = json.loads((output_dir / "management_quality_manifest.json").read_text(encoding="utf-8"))
    return summary, dimensions, evidence, validation, manifest


def test_management_quality_builder_aggregates_longitudinal_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_positive_fixture(tmp_path, "acme")

    ManagementQualityBuilder(company="acme").build()
    summary, dimensions, evidence, validation, manifest = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert summary["overall_view"] in {"strong", "reasonably_strong"}
    assert summary["overall_direction"] in {"improving", "stable", "mixed"}
    assert summary["strongest_dimension"]
    assert summary["weakest_dimension"]
    assert len(dimensions["dimensions"]) == 8
    assert evidence["evidence_count"] >= 8
    assert manifest["dimension_count"] == 8
    assert manifest["validation_status"] == "pass"
    required = {
        "execution_discipline",
        "capital_allocation_discipline",
        "candor_and_consistency",
        "strategic_clarity",
        "risk_handling",
        "owner_alignment",
        "adaptability",
        "evidence_confidence",
    }
    assert required == {item["dimension"] for item in dimensions["dimensions"]}
    assert "management_score" not in json.dumps(summary).lower()
    assert "management_score" not in json.dumps(dimensions).lower()
    assert "management_score" not in json.dumps(evidence).lower()


def test_validator_rejects_management_score_field():
    summary = {
        "schema_version": "management_quality.v1",
        "generator_version": "management_quality_builder.v1",
        "company_slug": "acme",
        "latest_period": "fy24",
        "overall_view": "mixed",
        "overall_direction": "stable",
        "strongest_dimension": "execution_discipline",
        "weakest_dimension": "owner_alignment",
        "what_strengthened_conviction": [],
        "what_weakened_conviction": [],
        "what_remains_unproven": [],
        "major_turning_points": [],
        "evidence_confidence": {"level": "high", "basis": ["synthetic"], "limitations": []},
        "investor_implication": "unchanged",
        "unresolved_questions": [],
        "generated_at": "2026-08-08T00:00:00Z",
        "management_score": 82,
    }
    dimensions = {
        "schema_version": "management_quality.v1",
        "generator_version": "management_quality_builder.v1",
        "company_slug": "acme",
        "latest_period": "fy24",
        "dimensions": [
            {
                "dimension": "execution_discipline",
                "assessment": "insufficient_evidence",
                "direction": "unclear",
                "what_strengthened": [],
                "what_weakened": [],
                "what_remains_unproven": [],
                "supporting_evidence": [],
                "conflicting_evidence": [],
                "confidence": {"level": "low", "basis": [], "limitations": []},
                "investor_implication": "unknown",
                "latest_period": "fy24",
                "evidence_ids": [],
                "source_streams": [],
            }
        ]
        + [
            {
                "dimension": dim,
                "assessment": "insufficient_evidence" if dim != "evidence_confidence" else "insufficient",
                "direction": "unclear",
                "what_strengthened": [],
                "what_weakened": [],
                "what_remains_unproven": [],
                "supporting_evidence": [],
                "conflicting_evidence": [],
                "confidence": {"level": "low", "basis": [], "limitations": []},
                "investor_implication": "unknown",
                "latest_period": "fy24",
                "evidence_ids": [],
                "source_streams": [],
            }
            for dim in [
                "capital_allocation_discipline",
                "candor_and_consistency",
                "strategic_clarity",
                "risk_handling",
                "owner_alignment",
                "adaptability",
                "evidence_confidence",
            ]
        ],
        "generated_at": "2026-08-08T00:00:00Z",
    }
    evidence = {"schema_version": "management_quality.v1", "generator_version": "management_quality_builder.v1", "company_slug": "acme", "latest_period": "fy24", "evidence_count": 0, "evidence_items": [], "turning_points": [], "generated_at": "2026-08-08T00:00:00Z"}

    validation = validate_management_quality_payload(summary, dimensions_payload=dimensions, evidence_payload=evidence)

    assert validation["status"] == "fail"
    assert any(issue["code"] == "public_term_leak" for issue in validation["issues"])


def test_capital_allocation_evidence_is_not_routed_into_owner_alignment_and_is_capped():
    source_payloads = {
        "commitments": [],
        "projects": [],
        "capacity": [],
        "risks": [],
        "commentary": [],
        "capital_allocation_outcomes": [
            {
                "allocation_id": "CAO-1",
                "allocation_name": "Capacity expansion",
                "allocation_category": "capacity_expansion",
                "outcome_status": "clearly_observed",
                "operating_outcome": "Plant commissioned.",
                "financial_outcome": "Returns are beginning to show.",
                "per_share_outcome": "Per-share economics look better.",
                "return_evidence": [{"period": "fy24"}],
                "confidence": {"level": "high", "basis": ["capital timeline"], "limitations": []},
                "source_references": [{"source_artifact": "capital_allocation_financial_timeline.json", "source_item_id": "ca1", "period": "fy24"}],
                "current_status": "deployed",
            }
        ],
        "owner_earnings": [],
        "per_share_compounding": [],
        "financial_truth": {},
    }

    evidence = build_management_quality_evidence(source_payloads, company_slug="acme")
    capital_items = [item for item in evidence if item.get("source_stream") == "capital_allocation_outcomes"]
    assert capital_items
    assert all(item["dimensions"] == ["capital_allocation_discipline", "evidence_confidence"] for item in capital_items)

    records, _ = evaluate_dimensions(
        evidence_items=evidence,
        source_stream_counts={"capital_allocation_outcomes": len(capital_items)},
        latest_period="fy24",
    )
    capital_dimension = next(item for item in records if item["dimension"] == "capital_allocation_discipline")
    assert capital_dimension["confidence"]["level"] in {"low", "medium", "insufficient"}
    assert any("capped" in limitation.lower() for limitation in capital_dimension["confidence"]["limitations"])
