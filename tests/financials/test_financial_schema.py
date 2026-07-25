from pathlib import Path

from knowledge.financials.schema import FinancialStatements, create_empty_financial_statements
from knowledge.financials.units import build_monetary_value
from knowledge.financials.validators import validate_financial_statements


def test_schema_required_sections_exist():
    statements = create_empty_financial_statements()

    assert isinstance(statements, FinancialStatements)
    assert hasattr(statements, "profit_and_loss")
    assert hasattr(statements, "balance_sheet")
    assert hasattr(statements, "cash_flow")
    assert hasattr(statements, "share_data")
    assert hasattr(statements, "corporate_actions")
    assert hasattr(statements, "shareholding_pattern")


def test_validator_accepts_missing_values_with_warnings():
    statements = create_empty_financial_statements()

    result = validate_financial_statements(statements)

    assert not result.errors
    assert result.warnings


def test_validator_requires_value_crore_when_original_value_present():
    statements = create_empty_financial_statements()
    statements.profit_and_loss.revenue.value_original = 100
    statements.profit_and_loss.revenue.unit_original = "crore"
    statements.profit_and_loss.revenue.value_crore = None

    result = validate_financial_statements(statements)

    assert "profit_and_loss.revenue.value_crore is required when value_original is present" in result.errors


def test_balance_sheet_equation_warning_if_available():
    statements = create_empty_financial_statements()
    statements.balance_sheet.equity_share_capital = build_monetary_value(
        value_original=100,
        unit_original="crore",
        source_year="fy25",
    )
    statements.balance_sheet.reserves = build_monetary_value(
        value_original=200,
        unit_original="crore",
        source_year="fy25",
    )
    statements.balance_sheet.net_worth = build_monetary_value(
        value_original=250,
        unit_original="crore",
        source_year="fy25",
    )
    statements.balance_sheet.total_assets = build_monetary_value(
        value_original=1000,
        unit_original="crore",
        source_year="fy25",
    )
    statements.balance_sheet.total_liabilities = build_monetary_value(
        value_original=900,
        unit_original="crore",
        source_year="fy25",
    )

    result = validate_financial_statements(statements)

    assert any("balance_sheet.net_worth" in warning for warning in result.warnings)
    assert any("balance_sheet equation warning" in warning for warning in result.warnings)


def test_no_llm_calculated_ratio_fields_allowed_in_schema_layer():
    payload = create_empty_financial_statements().to_dict()
    payload["financial_ratios"] = {"roe": 22.0}

    result = validate_financial_statements(payload)

    assert "financial_ratios is not allowed in the financial schema layer" in result.errors


def test_no_company_specific_logic_in_financial_package():
    root = Path("knowledge/financials")
    text = "\n".join(path.read_text(encoding="utf-8").lower() for path in root.glob("*.py"))

    assert "polymatech" not in text
    assert "tanla" not in text
    assert "tips" not in text
