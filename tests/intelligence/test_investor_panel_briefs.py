from intelligence.investor_panel.briefs import (
    MAX_BRIEF_BOTTOM_LINE_CHARS,
    MAX_BRIEF_BULLET_CHARS,
    normalize_user_facing_brief_lengths,
    normalize_user_facing_brief_shape,
    sanitize_user_facing_brief,
    validate_user_facing_brief,
)


def _brief():
    return {
        "title": "Buffett School of Thought: Business Quality & Capital Allocation",
        "lens": "This lens focuses on business quality, capital allocation, and the strength of the available evidence.",
        "what_looks_good": ["The PCIM shows durable demand and evidence_ids are cited clearly."],
        "what_needs_caution": ["The CIM still leaves some uncertainty around capital discipline."],
        "what_is_missing": ["The source_manifest suggests incomplete coverage in places."],
        "bottom_line": "This input_pack points to a solid business, but multi_year_inputs are still limited.",
    }


def test_sanitize_user_facing_brief_repairs_pcim_and_internal_terms():
    sanitized = sanitize_user_facing_brief(_brief())

    assert "PCIM" not in sanitized["what_looks_good"]
    assert "CIM" not in sanitized["what_needs_caution"]
    assert "source_manifest" not in sanitized["what_is_missing"]
    assert "input_pack" not in sanitized["bottom_line"]
    assert "multi_year_inputs" not in sanitized["bottom_line"]
    assert "available evidence" in sanitized["what_looks_good"][0].lower()
    assert "multi-year evidence" in sanitized["bottom_line"]


def test_sanitize_user_facing_brief_repairs_evidence_id_language():
    brief = _brief()
    brief["what_looks_good"] = ["The evidence_id trail is clear."]
    brief["bottom_line"] = "The evidence ids are limited, but the picture is still usable."

    sanitized = sanitize_user_facing_brief(brief)

    assert "evidence_id" not in sanitized["what_looks_good"][0].lower()
    assert "evidence ids" not in sanitized["bottom_line"].lower()
    assert "supporting evidence" in sanitized["what_looks_good"][0].lower()
    assert "supporting evidence" in sanitized["bottom_line"].lower()


def test_repaired_brief_passes_validation():
    sanitized = sanitize_user_facing_brief(_brief())
    validated = validate_user_facing_brief("buffett", sanitized)

    assert validated["title"] == "Buffett School of Thought: Business Quality & Capital Allocation"


def test_normalize_user_facing_brief_shape_converts_string_list_field():
    brief = _brief()
    brief["what_looks_good"] = "Strong demand is visible."

    normalized = normalize_user_facing_brief_shape(brief)

    assert normalized["what_looks_good"] == ["Strong demand is visible."]


def test_normalize_user_facing_brief_shape_converts_null_to_empty_list():
    brief = _brief()
    brief["what_needs_caution"] = None

    normalized = normalize_user_facing_brief_shape(brief)

    assert normalized["what_needs_caution"] == []


def test_normalize_user_facing_brief_shape_fills_missing_list_field():
    brief = _brief()
    brief.pop("what_is_missing")

    normalized = normalize_user_facing_brief_shape(brief)

    assert normalized["what_is_missing"] == []


def test_sanitizer_preserves_list_shape_after_internal_term_repair():
    brief = _brief()
    brief["what_looks_good"] = "The PCIM supports durable demand."

    normalized = normalize_user_facing_brief_shape(brief)
    sanitized = sanitize_user_facing_brief(normalized)

    assert isinstance(sanitized["what_looks_good"], list)
    assert "pcim" not in sanitized["what_looks_good"][0].lower()


def test_sanitizer_does_not_mask_recommendation_language():
    brief = _brief()
    brief["bottom_line"] = "This looks like a buy despite the gaps."

    sanitized = sanitize_user_facing_brief(brief)

    try:
        validate_user_facing_brief("buffett", sanitized)
    except ValueError as exc:
        assert "recommendation language" in str(exc)
    else:
        raise AssertionError("Expected recommendation language validation to fail")


def test_sanitizer_does_not_mask_valuation_language():
    brief = _brief()
    brief["bottom_line"] = "The stock looks undervalued based on the available evidence."

    sanitized = sanitize_user_facing_brief(brief)

    try:
        validate_user_facing_brief("buffett", sanitized)
    except ValueError as exc:
        assert "recommendation language" in str(exc) or "forbidden" in str(exc)
    else:
        raise AssertionError("Expected valuation language validation to fail")


def test_normalize_user_facing_brief_lengths_shortens_long_what_looks_good_item():
    brief = _brief()
    brief["what_looks_good"] = [
        "Demand remains resilient. " + ("Additional supporting detail " * 40),
    ]

    normalized = normalize_user_facing_brief_lengths(brief)

    assert len(normalized["what_looks_good"][0]) <= MAX_BRIEF_BULLET_CHARS
    assert normalized["what_looks_good"][0].endswith(".")


def test_normalize_user_facing_brief_lengths_shortens_long_what_needs_caution_item():
    brief = _brief()
    brief["what_needs_caution"] = [
        "Execution still looks uneven without enough proof. " + ("Follow-through remains uncertain " * 30),
    ]

    normalized = normalize_user_facing_brief_lengths(brief)

    assert len(normalized["what_needs_caution"][0]) <= MAX_BRIEF_BULLET_CHARS


def test_normalize_user_facing_brief_lengths_shortens_long_what_is_missing_item():
    brief = _brief()
    brief["what_is_missing"] = [
        "Cash flow detail is still sparse. " + ("More disclosure would improve confidence " * 30),
    ]

    normalized = normalize_user_facing_brief_lengths(brief)

    assert len(normalized["what_is_missing"][0]) <= MAX_BRIEF_BULLET_CHARS


def test_normalize_user_facing_brief_lengths_enforces_bottom_line_limit():
    brief = _brief()
    brief["bottom_line"] = "Evidence remains incomplete. " + ("More disclosure is still needed " * 80)

    normalized = normalize_user_facing_brief_lengths(brief)

    assert len(normalized["bottom_line"]) <= MAX_BRIEF_BOTTOM_LINE_CHARS


def test_normalize_user_facing_brief_lengths_prefers_sentence_boundary_truncation():
    brief = _brief()
    brief["what_looks_good"] = [
        "The company has a durable niche. "
        + ("This trailing detail keeps going without changing the main point " * 20)
    ]

    normalized = normalize_user_facing_brief_lengths(brief)

    assert normalized["what_looks_good"][0] == "The company has a durable niche."
