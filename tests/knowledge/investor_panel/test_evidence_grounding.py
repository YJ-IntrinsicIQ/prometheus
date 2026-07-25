import json

from intelligence.investor_panel.evidence_grounding import (
    assert_no_source_chunk,
    build_evidence_lookup,
    canonicalize_evidence_ids,
    normalize_evidence_id,
    normalize_evidence_ids_with_summary,
    normalize_text_evidence_ids,
    strip_inline_evidence_prose,
    split_claim_text,
    validate_analyst_evidence_grounding,
    validate_prompt_payload,
)


def _sample_pcim():
    return {
        "risk_inputs": {
            "risk_by_year": [
                {
                    "year": "fy25",
                    "items": [
                        {
                            "value": "Liquidity risk arising from borrowings",
                            "category": "Liquidity risk",
                            "signal_type": "risk_signal",
                            "source_year": "fy25",
                            "source_artifact": "company_intelligence.json",
                            "source_item_id": "RISK_1",
                            "page": 21,
                            "evidence_ids": ["ev_liquidity"],
                        },
                        {
                            "value": "Foreign currency risk from export receivables",
                            "category": "Foreign exchange exposure",
                            "source_year": "fy25",
                            "source_artifact": "company_intelligence.json",
                            "source_item_id": "RISK_2",
                            "page": 22,
                            "evidence_ids": ["ev_fx"],
                        },
                        {
                            "value": "Interest rate risk on variable-rate debt",
                            "category": "Interest rate risk",
                            "source_year": "fy25",
                            "source_artifact": "company_intelligence.json",
                            "source_item_id": "RISK_3",
                            "page": 23,
                            "evidence_ids": ["ev_rate"],
                        },
                        {
                            "value": "FEMA compliance risk",
                            "category": "FEMA compliance risk",
                            "source_year": "fy25",
                            "source_artifact": "company_intelligence.json",
                            "source_item_id": "RISK_4",
                            "page": 24,
                            "evidence_ids": ["ev_reg"],
                        },
                    ],
                }
            ]
        },
        "capital_allocation_inputs": {
            "capital_allocation_by_year": [
                {
                    "year": "fy25",
                    "items": [
                        {
                            "value": "Capital Work-in-Progress buildout",
                            "category": "cwip",
                            "amount": "200.0",
                            "source_year": "fy25",
                            "source_artifact": "company_intelligence.json",
                            "source_item_id": "CAP_1",
                            "page": 31,
                            "evidence_ids": ["ev_cwip"],
                        },
                        {
                            "value": "Treasury investments parked in debt mutual fund schemes",
                            "category": "treasury_investment",
                            "source_year": "fy25",
                            "source_artifact": "company_intelligence.json",
                            "source_item_id": "CAP_1B",
                            "page": 31,
                            "evidence_ids": ["ev_treasury"],
                        },
                        {
                            "value": "Share split approved",
                            "category": "share_split",
                            "source_year": "fy25",
                            "source_artifact": "company_intelligence.json",
                            "source_item_id": "CAP_2",
                            "page": 32,
                            "evidence_ids": ["ev_split"],
                        },
                    ],
                }
            ]
        },
        "multi_year_inputs": {
            "years_covered": ["fy24", "fy25"],
            "limitations": ["Only two years available."],
            "recurring_risks": {
                "recurring_risks": [
                    {
                        "risk_id": "risk_liquidity_risk",
                        "normalized_risk": "liquidity_risk",
                        "source_mentions": [
                            {
                                "value": "Liquidity risk from borrowings",
                                "source_year": "fy25",
                                "source_artifact": "company_intelligence.json",
                                "source_item_id": "RISK_1",
                                "source_page": 21,
                                "evidence_ids": ["ev_my_liquidity"],
                            }
                        ],
                        "related_evidence_ids": ["ev_my_liquidity"],
                    }
                ]
            },
            "evidence_map": {
                "ev_my_liquidity": {
                    "source_year": "fy25",
                    "source_artifact": "company_intelligence.json",
                    "source_item_id": "RISK_1",
                    "source_page": 21,
                }
            },
        },
        "evidence_map": {
            "risk_inputs": ["ev_liquidity", "ev_fx", "ev_rate", "ev_reg"],
            "capital_allocation_inputs": ["ev_cwip", "ev_split"],
            "multi_year_inputs": ["ev_my_liquidity"],
        },
        "available_years": ["fy25"],
        "uncertainty_missing_data": {
            "missing_sections": [
                {
                    "year": "fy25",
                    "section": "financial_strength_inputs",
                    "reason": "Operating cash flow and free cash flow are not available in the current evidence.",
                }
            ]
        },
    }


def test_build_evidence_lookup_captures_fields():
    lookup = build_evidence_lookup(_sample_pcim())

    assert lookup["ev_liquidity"]["category"] == "Liquidity risk"
    assert lookup["ev_liquidity"]["value"] == "Liquidity risk arising from borrowings"
    assert lookup["ev_liquidity"]["source_year"] == "fy25"
    assert lookup["ev_liquidity"]["source_item_id"] == "RISK_1"
    assert "risk_inputs" in lookup["ev_liquidity"]["section_path"]


def test_build_evidence_lookup_handles_missing_category_gracefully():
    pcim = _sample_pcim()
    pcim["risk_inputs"]["risk_by_year"][0]["items"][0].pop("category")
    lookup = build_evidence_lookup(pcim)

    assert lookup["ev_liquidity"]["category"] is None


def test_build_evidence_lookup_supports_company_intelligence_aliases():
    pcim = _sample_pcim()
    pcim["risk_inputs"]["risk_by_year"][0]["items"][0]["evidence_ids"] = [
        "ev_fy24_company_intelligence_json_risk_00003"
    ]
    lookup = build_evidence_lookup(pcim)

    assert lookup["ev_fy24_company_intelligence_risk_00003"]["canonical_evidence_id"] == (
        "ev_fy24_company_intelligence_json_risk_00003"
    )


def test_build_evidence_lookup_supports_business_classification_aliases():
    pcim = _sample_pcim()
    pcim["business_understanding"] = {
        "business_dna_by_year": [
            {
                "year": "fy25",
                "items": [
                    {
                        "value": "Manufacturing",
                        "source_year": "fy25",
                        "source_artifact": "business_classification.json",
                        "source_item_id": "Manufacturing",
                        "evidence_ids": [
                            "ev_fy25_business_classification_json_business_dna_by_year_fy25_manufacturing"
                        ],
                    }
                ],
            }
        ]
    }
    lookup = build_evidence_lookup(pcim)

    assert lookup["ev_fy25_business_classification_manufacturing"]["canonical_evidence_id"] == (
        "ev_fy25_business_classification_json_business_dna_by_year_fy25_manufacturing"
    )


def test_build_evidence_lookup_supports_export_and_semiconductor_business_classification_aliases():
    pcim = _sample_pcim()
    pcim["business_understanding"] = {
        "business_dna_by_year": [
            {
                "year": "fy24",
                "items": [
                    {
                        "value": "Export",
                        "source_year": "fy24",
                        "source_artifact": "business_classification.json",
                        "source_item_id": "Export",
                        "evidence_ids": [
                            "ev_fy24_business_classification_json_business_dna_by_year_fy24_export"
                        ],
                    }
                ],
            },
            {
                "year": "fy25",
                "items": [
                    {
                        "value": "Semiconductor",
                        "source_year": "fy25",
                        "source_artifact": "business_classification.json",
                        "source_item_id": "Semiconductor",
                        "evidence_ids": [
                            "ev_fy25_business_classification_json_business_dna_by_year_fy25_semiconductor"
                        ],
                    }
                ],
            },
        ]
    }
    lookup = build_evidence_lookup(pcim)

    assert lookup["ev_fy24_business_classification_export"]["canonical_evidence_id"] == (
        "ev_fy24_business_classification_json_business_dna_by_year_fy24_export"
    )
    assert lookup["ev_fy25_business_classification_semiconductor"]["canonical_evidence_id"] == (
        "ev_fy25_business_classification_json_business_dna_by_year_fy25_semiconductor"
    )


def test_normalize_evidence_id_adds_missing_json_segment():
    assert normalize_evidence_id("ev_fy24_company_intelligence_risk_00003") == (
        "ev_fy24_company_intelligence_json_risk_00003"
    )
    assert normalize_evidence_id("ev_fy25_company_intelligence_capalloc_00002") == (
        "ev_fy25_company_intelligence_json_capalloc_00002"
    )
    assert normalize_evidence_id("ev_fy24_company_intelligence_prom_00001") == (
        "ev_fy24_company_intelligence_json_prom_00001"
    )
    assert normalize_evidence_id("ev_fy25_company_intelligence_prom_00001") == (
        "ev_fy25_company_intelligence_json_prom_00001"
    )


def test_canonicalize_evidence_ids_maps_alias_when_safe():
    pcim = _sample_pcim()
    pcim["business_understanding"] = {
        "business_dna_by_year": [
            {
                "year": "fy25",
                "items": [
                    {
                        "value": "Manufacturing",
                        "source_year": "fy25",
                        "source_artifact": "business_classification.json",
                        "source_item_id": "Manufacturing",
                        "evidence_ids": [
                            "ev_fy25_business_classification_json_business_dna_by_year_fy25_manufacturing"
                        ],
                    }
                ],
            }
        ]
    }
    lookup = build_evidence_lookup(pcim)
    normalized = canonicalize_evidence_ids(
        ["ev_fy25_business_classification_manufacturing"],
        lookup,
    )

    assert normalized == ["ev_fy25_business_classification_json_business_dna_by_year_fy25_manufacturing"]


def test_promise_alias_maps_when_canonical_id_exists():
    pcim = _sample_pcim()
    pcim["capital_allocation_inputs"]["promises_by_year"] = [
        {
            "year": "fy25",
            "items": [
                {
                    "value": "Maintain expansion plan",
                    "source_year": "fy25",
                    "source_artifact": "company_intelligence.json",
                    "source_item_id": "PROM_1",
                    "evidence_ids": ["ev_fy25_company_intelligence_json_prom_00001"],
                }
            ],
        }
    ]
    lookup = build_evidence_lookup(pcim)
    normalized, summary = normalize_evidence_ids_with_summary(
        ["ev_fy25_company_intelligence_prom_00001"],
        lookup,
    )

    assert normalized == ["ev_fy25_company_intelligence_json_prom_00001"]
    assert summary["replacements"] == [
        {
            "original_id": "ev_fy25_company_intelligence_prom_00001",
            "canonical_id": "ev_fy25_company_intelligence_json_prom_00001",
        }
    ]


def test_promise_alias_is_not_invented_when_canonical_id_missing():
    lookup = build_evidence_lookup(_sample_pcim())
    normalized, summary = normalize_evidence_ids_with_summary(
        ["ev_fy25_company_intelligence_prom_99999"],
        lookup,
    )

    assert normalized == ["ev_fy25_company_intelligence_prom_99999"]
    assert summary["unresolved_ids"] == ["ev_fy25_company_intelligence_prom_99999"]


def test_normalize_evidence_ids_with_summary_tracks_replacements_and_unresolved():
    pcim = _sample_pcim()
    pcim["risk_inputs"]["risk_by_year"][0]["items"][0]["evidence_ids"] = [
        "ev_fy24_company_intelligence_json_risk_00003"
    ]
    lookup = build_evidence_lookup(pcim)
    normalized, summary = normalize_evidence_ids_with_summary(
        [
            "ev_fy24_company_intelligence_risk_00003",
            "ev_unknown_alias",
            "ev_fy24_company_intelligence_risk_00003",
        ],
        lookup,
    )

    assert normalized == [
        "ev_fy24_company_intelligence_json_risk_00003",
        "ev_unknown_alias",
    ]
    assert summary["applied"] is True
    assert summary["replacements"] == [
        {
            "original_id": "ev_fy24_company_intelligence_risk_00003",
            "canonical_id": "ev_fy24_company_intelligence_json_risk_00003",
        }
    ]
    assert summary["unresolved_ids"] == ["ev_unknown_alias"]


def test_normalize_text_evidence_ids_rewrites_safe_inline_ids():
    pcim = _sample_pcim()
    pcim["risk_inputs"]["risk_by_year"][0]["items"][0]["evidence_ids"] = [
        "ev_fy24_company_intelligence_json_risk_00003"
    ]
    lookup = build_evidence_lookup(pcim)
    normalized_text, replacements, unresolved = normalize_text_evidence_ids(
        "See ev_fy24_company_intelligence_risk_00003 for support.",
        lookup,
    )

    assert "ev_fy24_company_intelligence_json_risk_00003" in normalized_text
    assert replacements == [
        {
            "original_id": "ev_fy24_company_intelligence_risk_00003",
            "canonical_id": "ev_fy24_company_intelligence_json_risk_00003",
        }
    ]
    assert unresolved == []


def test_strip_inline_evidence_prose_removes_supporting_evidence_fragment():
    stripped, inline_ids = strip_inline_evidence_prose(
        "Liquidity risk remains material. (supporting evidence: ev_a; ev_b; note: cash flow missing)."
    )

    assert stripped == "Liquidity risk remains material."
    assert inline_ids == ["ev_a", "ev_b"]


def test_split_claim_text_does_not_create_fake_claim_fragments_from_inline_evidence():
    claim = (
        "Downside protection remains mixed. "
        "(supporting evidence: ev_fy25_company_intelligence_json_risk_00001; "
        "ev_fy25_company_intelligence_json_capalloc_00002)."
    )

    units = split_claim_text(claim)

    assert units == ["Downside protection remains mixed"]


def test_canonicalize_evidence_ids_does_not_invent_unsafe_ids():
    lookup = build_evidence_lookup(_sample_pcim())

    assert canonicalize_evidence_ids(["ev_unknown_alias"], lookup) == ["ev_unknown_alias"]


def test_split_claim_text_breaks_broad_assessment_into_units():
    claim = (
        "Available disclosures show liquidity and refinancing concerns; "
        "interest-rate exposure remains elevated; "
        "CWIP is material and treasury investments are present, "
        "but operating cash flow is not available."
    )

    units = split_claim_text(claim)

    assert any("liquidity" in unit.lower() for unit in units)
    assert any("interest-rate" in unit.lower() for unit in units)
    assert any("cwip" in unit.lower() for unit in units)
    assert any("treasury" in unit.lower() for unit in units)
    assert any("operating cash flow" in unit.lower() for unit in units)


def test_liquidity_claim_accepts_liquidity_evidence():
    result = validate_analyst_evidence_grounding(
        assessment={},
        key_findings=["Liquidity risk is worsening."],
        red_flags=[],
        open_uncertainties=[],
        claim_evidence_map={"key_findings.0": ["ev_liquidity"]},
        supporting_pcim_sections=["risk_inputs"],
        consumed_sections=["risk_inputs"],
        supplied_evidence_ids=["ev_liquidity"],
        evidence_lookup=build_evidence_lookup(_sample_pcim()),
    )
    assert result["evidence_grounding_status"] == "pass"


def test_liquidity_claim_rejects_fx_evidence():
    result = validate_analyst_evidence_grounding(
        assessment={},
        key_findings=["Liquidity risk is worsening."],
        red_flags=[],
        open_uncertainties=[],
        claim_evidence_map={"key_findings.0": ["ev_fx"]},
        supporting_pcim_sections=["risk_inputs"],
        consumed_sections=["risk_inputs"],
        supplied_evidence_ids=["ev_fx"],
        evidence_lookup=build_evidence_lookup(_sample_pcim()),
    )
    assert result["evidence_grounding_status"] == "fail"


def test_interest_rate_claim_accepts_interest_rate_evidence():
    result = validate_analyst_evidence_grounding(
        assessment={},
        key_findings=[],
        red_flags=["Interest-rate sensitivity remains elevated."],
        open_uncertainties=[],
        claim_evidence_map={"red_flags.0": ["ev_rate"]},
        supporting_pcim_sections=["risk_inputs"],
        consumed_sections=["risk_inputs"],
        supplied_evidence_ids=["ev_rate"],
        evidence_lookup=build_evidence_lookup(_sample_pcim()),
    )
    assert result["evidence_grounding_status"] == "pass"


def test_interest_rate_claim_rejects_fx_evidence():
    result = validate_analyst_evidence_grounding(
        assessment={},
        key_findings=[],
        red_flags=["Interest-rate sensitivity remains elevated."],
        open_uncertainties=[],
        claim_evidence_map={"red_flags.0": ["ev_fx"]},
        supporting_pcim_sections=["risk_inputs"],
        consumed_sections=["risk_inputs"],
        supplied_evidence_ids=["ev_fx"],
        evidence_lookup=build_evidence_lookup(_sample_pcim()),
    )
    assert result["evidence_grounding_status"] == "fail"


def test_fx_claim_accepts_fx_evidence():
    result = validate_analyst_evidence_grounding(
        assessment={},
        key_findings=["Foreign exchange exposure remains material."],
        red_flags=[],
        open_uncertainties=[],
        claim_evidence_map={"key_findings.0": ["ev_fx"]},
        supporting_pcim_sections=["risk_inputs"],
        consumed_sections=["risk_inputs"],
        supplied_evidence_ids=["ev_fx"],
        evidence_lookup=build_evidence_lookup(_sample_pcim()),
    )
    assert result["evidence_grounding_status"] == "pass"


def test_fx_claim_rejects_liquidity_evidence():
    result = validate_analyst_evidence_grounding(
        assessment={},
        key_findings=["Foreign exchange exposure remains material."],
        red_flags=[],
        open_uncertainties=[],
        claim_evidence_map={"key_findings.0": ["ev_liquidity"]},
        supporting_pcim_sections=["risk_inputs"],
        consumed_sections=["risk_inputs"],
        supplied_evidence_ids=["ev_liquidity"],
        evidence_lookup=build_evidence_lookup(_sample_pcim()),
    )
    assert result["evidence_grounding_status"] == "fail"


def test_regulatory_claim_accepts_fema_evidence():
    result = validate_analyst_evidence_grounding(
        assessment={},
        key_findings=["Regulatory risk remains present."],
        red_flags=[],
        open_uncertainties=[],
        claim_evidence_map={"key_findings.0": ["ev_reg"]},
        supporting_pcim_sections=["risk_inputs"],
        consumed_sections=["risk_inputs"],
        supplied_evidence_ids=["ev_reg"],
        evidence_lookup=build_evidence_lookup(_sample_pcim()),
    )
    assert result["evidence_grounding_status"] == "pass"


def test_capex_claim_accepts_cwip_evidence():
    result = validate_analyst_evidence_grounding(
        assessment={},
        key_findings=["CWIP remains a material capital allocation item."],
        red_flags=[],
        open_uncertainties=[],
        claim_evidence_map={"key_findings.0": ["ev_cwip"]},
        supporting_pcim_sections=["capital_allocation_inputs"],
        consumed_sections=["capital_allocation_inputs"],
        supplied_evidence_ids=["ev_cwip"],
        evidence_lookup=build_evidence_lookup(_sample_pcim()),
    )
    assert result["evidence_grounding_status"] == "pass"


def test_share_split_claim_accepts_share_split_evidence():
    result = validate_analyst_evidence_grounding(
        assessment={},
        key_findings=["The year included a share split."],
        red_flags=[],
        open_uncertainties=[],
        claim_evidence_map={"key_findings.0": ["ev_split"]},
        supporting_pcim_sections=["capital_allocation_inputs"],
        consumed_sections=["capital_allocation_inputs"],
        supplied_evidence_ids=["ev_split"],
        evidence_lookup=build_evidence_lookup(_sample_pcim()),
    )
    assert result["evidence_grounding_status"] == "pass"


def test_treasury_claim_accepts_treasury_evidence():
    result = validate_analyst_evidence_grounding(
        assessment={},
        key_findings=["Treasury investments remain present."],
        red_flags=[],
        open_uncertainties=[],
        claim_evidence_map={"key_findings.0": ["ev_treasury"]},
        supporting_pcim_sections=["capital_allocation_inputs"],
        consumed_sections=["capital_allocation_inputs"],
        supplied_evidence_ids=["ev_treasury"],
        evidence_lookup=build_evidence_lookup(_sample_pcim()),
    )
    assert result["evidence_grounding_status"] == "pass"


def test_missing_evidence_id_returns_fail():
    result = validate_analyst_evidence_grounding(
        assessment={},
        key_findings=["Liquidity remains a concern."],
        red_flags=[],
        open_uncertainties=[],
        claim_evidence_map={"key_findings.0": ["ev_missing"]},
        supporting_pcim_sections=["risk_inputs"],
        consumed_sections=["risk_inputs"],
        supplied_evidence_ids=["ev_missing"],
        evidence_lookup=build_evidence_lookup(_sample_pcim()),
    )
    assert result["evidence_grounding_status"] == "fail"


def test_mixed_valid_invalid_evidence_ignores_unrelated_extra_support():
    result = validate_analyst_evidence_grounding(
        assessment={},
        key_findings=["Liquidity remains a concern."],
        red_flags=[],
        open_uncertainties=[],
        claim_evidence_map={"key_findings.0": ["ev_liquidity", "ev_fx"]},
        supporting_pcim_sections=["risk_inputs"],
        consumed_sections=["risk_inputs"],
        supplied_evidence_ids=["ev_liquidity", "ev_fx"],
        evidence_lookup=build_evidence_lookup(_sample_pcim()),
    )
    assert result["evidence_grounding_status"] == "pass"
    assert result["evidence_grounding_warnings"] == []


def test_liquidity_claim_ignores_unrelated_share_split_when_supported():
    result = validate_analyst_evidence_grounding(
        assessment={},
        key_findings=["Liquidity remains a concern."],
        red_flags=[],
        open_uncertainties=[],
        claim_evidence_map={"key_findings.0": ["ev_liquidity", "ev_split"]},
        supporting_pcim_sections=["risk_inputs", "capital_allocation_inputs"],
        consumed_sections=["risk_inputs", "capital_allocation_inputs"],
        supplied_evidence_ids=["ev_liquidity", "ev_split"],
        evidence_lookup=build_evidence_lookup(_sample_pcim()),
    )

    assert result["evidence_grounding_status"] == "pass"
    assert result["evidence_grounding_warnings"] == []


def test_interest_rate_claim_ignores_fx_when_supported():
    result = validate_analyst_evidence_grounding(
        assessment={},
        key_findings=["Interest-rate sensitivity remains elevated."],
        red_flags=[],
        open_uncertainties=[],
        claim_evidence_map={"key_findings.0": ["ev_rate", "ev_fx"]},
        supporting_pcim_sections=["risk_inputs"],
        consumed_sections=["risk_inputs"],
        supplied_evidence_ids=["ev_rate", "ev_fx"],
        evidence_lookup=build_evidence_lookup(_sample_pcim()),
    )

    assert result["evidence_grounding_status"] == "pass"
    assert result["evidence_grounding_warnings"] == []


def test_missing_cash_flow_claim_validates_against_uncertainty_section():
    result = validate_analyst_evidence_grounding(
        assessment={"financial_strength_assessment": "Operating cash flow is not available in the reviewed materials."},
        key_findings=[],
        red_flags=[],
        open_uncertainties=[],
        claim_evidence_map={"assessment.financial_strength_assessment": []},
        supporting_pcim_sections=["uncertainty_missing_data"],
        consumed_sections=["uncertainty_missing_data"],
        supplied_evidence_ids=[],
        evidence_lookup=build_evidence_lookup(_sample_pcim()),
    )

    assert result["evidence_grounding_status"] == "pass"


def test_promise_evidence_supports_promise_follow_through_uncertainty():
    pcim = _sample_pcim()
    pcim["capital_allocation_inputs"]["promises_by_year"] = [
        {
            "year": "fy25",
            "items": [
                {
                    "value": "Maintain expansion plan",
                    "source_year": "fy25",
                    "source_artifact": "company_intelligence.json",
                    "source_item_id": "PROM_1",
                    "evidence_ids": ["ev_fy25_company_intelligence_json_prom_00001"],
                }
            ],
        }
    ]
    result = validate_analyst_evidence_grounding(
        assessment={},
        key_findings=[],
        red_flags=[],
        open_uncertainties=["Promise follow-through remains unclear."],
        claim_evidence_map={"open_uncertainties.0": ["ev_fy25_company_intelligence_json_prom_00001"]},
        supporting_pcim_sections=["capital_allocation_inputs", "multi_year_inputs"],
        consumed_sections=["capital_allocation_inputs", "multi_year_inputs"],
        supplied_evidence_ids=["ev_fy25_company_intelligence_json_prom_00001"],
        evidence_lookup=build_evidence_lookup(pcim),
    )

    assert result["evidence_grounding_status"] == "pass"


def test_promise_evidence_is_ignored_for_liquidity_claim():
    pcim = _sample_pcim()
    pcim["capital_allocation_inputs"]["promises_by_year"] = [
        {
            "year": "fy25",
            "items": [
                {
                    "value": "Maintain expansion plan",
                    "source_year": "fy25",
                    "source_artifact": "company_intelligence.json",
                    "source_item_id": "PROM_1",
                    "evidence_ids": ["ev_fy25_company_intelligence_json_prom_00001"],
                }
            ],
        }
    ]
    result = validate_analyst_evidence_grounding(
        assessment={},
        key_findings=["Liquidity remains a concern."],
        red_flags=[],
        open_uncertainties=[],
        claim_evidence_map={"key_findings.0": ["ev_liquidity", "ev_fy25_company_intelligence_json_prom_00001"]},
        supporting_pcim_sections=["risk_inputs", "capital_allocation_inputs"],
        consumed_sections=["risk_inputs", "capital_allocation_inputs"],
        supplied_evidence_ids=["ev_liquidity", "ev_fy25_company_intelligence_json_prom_00001"],
        evidence_lookup=build_evidence_lookup(pcim),
    )

    assert result["evidence_grounding_status"] == "pass"
    assert result["evidence_grounding_warnings"] == []


def test_promise_evidence_is_ignored_for_capex_claim():
    pcim = _sample_pcim()
    pcim["capital_allocation_inputs"]["promises_by_year"] = [
        {
            "year": "fy25",
            "items": [
                {
                    "value": "Maintain expansion plan",
                    "source_year": "fy25",
                    "source_artifact": "company_intelligence.json",
                    "source_item_id": "PROM_1",
                    "evidence_ids": ["ev_fy25_company_intelligence_json_prom_00001"],
                }
            ],
        }
    ]
    result = validate_analyst_evidence_grounding(
        assessment={},
        key_findings=["CWIP remains a material capital allocation item."],
        red_flags=[],
        open_uncertainties=[],
        claim_evidence_map={"key_findings.0": ["ev_cwip", "ev_fy25_company_intelligence_json_prom_00001"]},
        supporting_pcim_sections=["capital_allocation_inputs"],
        consumed_sections=["capital_allocation_inputs"],
        supplied_evidence_ids=["ev_cwip", "ev_fy25_company_intelligence_json_prom_00001"],
        evidence_lookup=build_evidence_lookup(pcim),
    )

    assert result["evidence_grounding_status"] == "pass"
    assert result["evidence_grounding_warnings"] == []


def test_promise_evidence_is_ignored_for_downside_protection_claim_without_promise_context():
    pcim = _sample_pcim()
    pcim["capital_allocation_inputs"]["promises_by_year"] = [
        {
            "year": "fy25",
            "items": [
                {
                    "value": "Maintain expansion plan",
                    "source_year": "fy25",
                    "source_artifact": "company_intelligence.json",
                    "source_item_id": "PROM_1",
                    "evidence_ids": ["ev_fy25_company_intelligence_json_prom_00001"],
                }
            ],
        }
    ]
    result = validate_analyst_evidence_grounding(
        assessment={"downside_protection_assessment": "Downside protection remains mixed because liquidity pressure is elevated."},
        key_findings=[],
        red_flags=[],
        open_uncertainties=[],
        claim_evidence_map={"assessment.downside_protection_assessment": ["ev_liquidity", "ev_fy25_company_intelligence_json_prom_00001"]},
        supporting_pcim_sections=["risk_inputs", "capital_allocation_inputs"],
        consumed_sections=["risk_inputs", "capital_allocation_inputs"],
        supplied_evidence_ids=["ev_liquidity", "ev_fy25_company_intelligence_json_prom_00001"],
        evidence_lookup=build_evidence_lookup(pcim),
    )

    assert result["evidence_grounding_status"] == "pass"


def test_governance_claim_rejects_market_risk_evidence():
    result = validate_analyst_evidence_grounding(
        assessment={"governance_sanity_assessment": "Governance oversight remains unclear."},
        key_findings=[],
        red_flags=[],
        open_uncertainties=[],
        claim_evidence_map={"assessment.governance_sanity_assessment": ["ev_fx"]},
        supporting_pcim_sections=["risk_inputs"],
        consumed_sections=["risk_inputs"],
        supplied_evidence_ids=["ev_fx"],
        evidence_lookup=build_evidence_lookup(_sample_pcim()),
    )

    assert result["evidence_grounding_status"] == "fail"
    assert any("market-risk evidence should not support governance/incentive claim" in warning["issue"] for warning in result["evidence_grounding_warnings"])


def test_market_risk_claim_accepts_market_risk_evidence():
    result = validate_analyst_evidence_grounding(
        assessment={"avoidable_risk_assessment": "Foreign exchange risk remains a real exposure."},
        key_findings=[],
        red_flags=[],
        open_uncertainties=[],
        claim_evidence_map={"assessment.avoidable_risk_assessment": ["ev_fx"]},
        supporting_pcim_sections=["risk_inputs"],
        consumed_sections=["risk_inputs"],
        supplied_evidence_ids=["ev_fx"],
        evidence_lookup=build_evidence_lookup(_sample_pcim()),
    )

    assert result["evidence_grounding_status"] == "pass"
    assert result["evidence_grounding_warnings"] == []


def test_generic_market_risk_claim_accepts_generic_market_risk_evidence():
    pcim = _sample_pcim()
    pcim["risk_inputs"]["risk_by_year"][0]["items"][1]["category"] = "Market risk"
    pcim["risk_inputs"]["risk_by_year"][0]["items"][1]["value"] = (
        "Sensitivity to market-price movements remains visible."
    )
    result = validate_analyst_evidence_grounding(
        assessment={"avoidable_risk_assessment": "Risk disclosures explicitly note market risk exposure."},
        key_findings=[],
        red_flags=[],
        open_uncertainties=[],
        claim_evidence_map={"assessment.avoidable_risk_assessment": ["ev_fx"]},
        supporting_pcim_sections=["risk_inputs"],
        consumed_sections=["risk_inputs"],
        supplied_evidence_ids=["ev_fx"],
        evidence_lookup=build_evidence_lookup(pcim),
    )

    assert result["evidence_grounding_status"] == "pass"
    assert result["evidence_grounding_warnings"] == []


def test_market_price_movement_claim_accepts_market_risk_evidence():
    pcim = _sample_pcim()
    pcim["risk_inputs"]["risk_by_year"][0]["items"][1]["category"] = "Market risk"
    pcim["risk_inputs"]["risk_by_year"][0]["items"][1]["value"] = (
        "Sensitivity to market-price movements remains visible."
    )
    result = validate_analyst_evidence_grounding(
        assessment={},
        key_findings=[
            "Risk disclosures explicitly note sensitivity to market-price movements."
        ],
        red_flags=[],
        open_uncertainties=[],
        claim_evidence_map={"key_findings.0": ["ev_fx"]},
        supporting_pcim_sections=["risk_inputs"],
        consumed_sections=["risk_inputs"],
        supplied_evidence_ids=["ev_fx"],
        evidence_lookup=build_evidence_lookup(pcim),
    )

    assert result["evidence_grounding_status"] == "pass"
    assert result["evidence_grounding_warnings"] == []


def test_governance_missing_data_claim_accepts_uncertainty_support():
    result = validate_analyst_evidence_grounding(
        assessment={"governance_sanity_assessment": "Board committee detail is not available in the reviewed materials."},
        key_findings=[],
        red_flags=[],
        open_uncertainties=[],
        claim_evidence_map={"assessment.governance_sanity_assessment": []},
        supporting_pcim_sections=["uncertainty_missing_data"],
        consumed_sections=["uncertainty_missing_data"],
        supplied_evidence_ids=[],
        evidence_lookup=build_evidence_lookup(_sample_pcim()),
    )

    assert result["evidence_grounding_status"] == "pass"


def test_related_party_governance_claim_accepts_governance_evidence():
    pcim = _sample_pcim()
    pcim["governance_and_incentive_inputs"] = {
        "related_party_and_control_items_by_year": [
            {
                "year": "fy25",
                "items": [
                    {
                        "value": "Related-party advance requires governance monitoring.",
                        "signal_type": "related_party_exposure",
                        "source_year": "fy25",
                        "source_artifact": "company_intelligence.json",
                        "source_item_id": "GOV_1",
                        "evidence_ids": ["ev_related_party"],
                    }
                ],
            }
        ]
    }
    result = validate_analyst_evidence_grounding(
        assessment={"governance_sanity_assessment": "Related-party exposure is a governance monitoring signal."},
        key_findings=[],
        red_flags=[],
        open_uncertainties=[],
        claim_evidence_map={"assessment.governance_sanity_assessment": ["ev_related_party"]},
        supporting_pcim_sections=["governance_and_incentive_inputs"],
        consumed_sections=["governance_and_incentive_inputs"],
        supplied_evidence_ids=["ev_related_party"],
        evidence_lookup=build_evidence_lookup(pcim),
    )

    assert result["evidence_grounding_status"] == "pass"
    assert result["evidence_grounding_warnings"] == []


def test_business_model_evidence_supports_business_quality_claim_without_warning():
    pcim = _sample_pcim()
    pcim["business_understanding"] = {
        "latest_business_view": {
            "business_model": {
                "business_summary": "Capital-intensive manufacturing business",
                "source_year": "fy25",
                "source_artifact": "company_intelligence.json",
                "source_item_id": "BUS_1",
                "evidence_ids": ["ev_business_model"],
            }
        }
    }
    result = validate_analyst_evidence_grounding(
        assessment={"business_quality_assessment": "Business quality is understandable from the operating model."},
        key_findings=[],
        red_flags=[],
        open_uncertainties=[],
        claim_evidence_map={"assessment.business_quality_assessment": ["ev_business_model"]},
        supporting_pcim_sections=["business_understanding"],
        consumed_sections=["business_understanding"],
        supplied_evidence_ids=["ev_business_model"],
        evidence_lookup=build_evidence_lookup(pcim),
    )

    assert result["evidence_grounding_status"] == "pass"
    assert result["evidence_grounding_warnings"] == []


def test_business_model_evidence_alone_does_not_prove_strong_moat():
    pcim = _sample_pcim()
    pcim["business_understanding"] = {
        "latest_business_view": {
            "business_model": {
                "business_summary": "Capital-intensive manufacturing business",
                "source_year": "fy25",
                "source_artifact": "company_intelligence.json",
                "source_item_id": "BUS_1",
                "evidence_ids": ["ev_business_model"],
            }
        }
    }
    result = validate_analyst_evidence_grounding(
        assessment={"moat_assessment": "The company has strong pricing power and a durable competitive advantage."},
        key_findings=[],
        red_flags=[],
        open_uncertainties=[],
        claim_evidence_map={"assessment.moat_assessment": ["ev_business_model"]},
        supporting_pcim_sections=["business_understanding"],
        consumed_sections=["business_understanding"],
        supplied_evidence_ids=["ev_business_model"],
        evidence_lookup=build_evidence_lookup(pcim),
    )

    assert result["evidence_grounding_status"] == "warning"
    assert any("business-model evidence supports business description" in warning["issue"] for warning in result["evidence_grounding_warnings"])


def test_normalized_evidence_id_returns_warning_with_metadata():
    pcim = _sample_pcim()
    pcim["risk_inputs"]["risk_by_year"][0]["items"][0]["evidence_ids"] = [
        "ev_fy24_company_intelligence_json_risk_00003"
    ]
    lookup = build_evidence_lookup(pcim)
    result = validate_analyst_evidence_grounding(
        assessment={},
        key_findings=["Liquidity remains a concern."],
        red_flags=[],
        open_uncertainties=[],
        claim_evidence_map={"key_findings.0": ["ev_fy24_company_intelligence_risk_00003"]},
        supporting_pcim_sections=["risk_inputs"],
        consumed_sections=["risk_inputs"],
        supplied_evidence_ids=["ev_fy24_company_intelligence_risk_00003"],
        evidence_lookup=lookup,
    )

    assert result["evidence_grounding_status"] == "warning"
    assert any(
        "ev_fy24_company_intelligence_json_risk_00003" in (w.get("normalized_ids") or [])
        for w in result["evidence_grounding_warnings"]
    )


def test_duplicate_warnings_are_removed_and_limited():
    result = validate_analyst_evidence_grounding(
        assessment={
            "financial_strength_assessment": "Liquidity remains a concern. Liquidity remains a concern.",
        },
        key_findings=["Liquidity remains a concern."],
        red_flags=["Liquidity remains a concern."],
        open_uncertainties=[],
        claim_evidence_map={
            "assessment.financial_strength_assessment": ["ev_fx"],
            "key_findings.0": ["ev_fx"],
            "red_flags.0": ["ev_fx"],
        },
        supporting_pcim_sections=["risk_inputs"],
        consumed_sections=["risk_inputs"],
        supplied_evidence_ids=["ev_fx"],
        evidence_lookup=build_evidence_lookup(_sample_pcim()),
    )

    assert len(result["evidence_grounding_warnings"]) <= 10


def test_broad_graham_assessment_produces_small_warning_set():
    claim = (
        "Available disclosures show escalating liquidity and refinancing concerns; "
        "interest-rate exposure is worsening; "
        "CWIP remains material; "
        "treasury investments are present; "
        "operating cash flow is not available in the reviewed materials."
    )
    result = validate_analyst_evidence_grounding(
        assessment={"financial_strength_assessment": claim},
        key_findings=[],
        red_flags=[],
        open_uncertainties=[],
        claim_evidence_map={
            "assessment.financial_strength_assessment": [
                "ev_liquidity",
                "ev_rate",
                "ev_cwip",
                "ev_treasury",
                "ev_split",
            ]
        },
        supporting_pcim_sections=["risk_inputs", "capital_allocation_inputs", "uncertainty_missing_data"],
        consumed_sections=["risk_inputs", "capital_allocation_inputs", "uncertainty_missing_data"],
        supplied_evidence_ids=["ev_liquidity", "ev_rate", "ev_cwip", "ev_treasury", "ev_split"],
        evidence_lookup=build_evidence_lookup(_sample_pcim()),
    )

    assert result["evidence_grounding_status"] in {"pass", "warning"}
    assert len(result["evidence_grounding_warnings"]) < 5


def test_prompt_payload_has_no_source_chunk_and_preserves_limitations():
    compact = {
        "multi_year_inputs": {
            "years_covered": ["fy24", "fy25"],
            "limitations": ["Only two years available."],
        }
    }
    validate_prompt_payload(compact, pcim_source="companies/acme/company_memory/pcim_v1.json")
    assert_no_source_chunk(compact)


def test_prompt_payload_rejects_raw_multi_year_source():
    compact = {
        "multi_year_inputs": {
            "years_covered": ["fy24", "fy25"],
            "limitations": ["Only two years available."],
        }
    }

    try:
        validate_prompt_payload(compact, pcim_source="companies/acme/company_memory/multi_year/multi_year_index.json")
    except ValueError as exc:
        assert "PCIM" in str(exc)
    else:
        raise AssertionError("Expected raw multi-year source to be rejected")


def test_prompt_payload_rejects_source_chunk():
    compact = {"risk_inputs": {"risk_by_year": [{"items": [{"source_chunk": "bad"}]}]}}
    try:
        validate_prompt_payload(compact, pcim_source="companies/acme/company_memory/pcim_v1.json")
    except ValueError as exc:
        assert "source_chunk leakage" in str(exc)
    else:
        raise AssertionError("Expected source_chunk leakage failure")


def test_prompt_payload_rejects_raw_multi_year_source():
    try:
        validate_prompt_payload({"multi_year_inputs": {"years_covered": ["fy24"], "limitations": []}}, pcim_source="companies/acme/company_memory/multi_year/risk_evolution.json")
    except ValueError as exc:
        assert "must load multi_year_inputs from PCIM" in str(exc)
    else:
        raise AssertionError("Expected raw multi-year source failure")
