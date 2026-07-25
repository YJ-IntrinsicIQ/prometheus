from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


FINANCIAL_SCHEMA_VERSION = "1.0"
DEFAULT_CURRENCY = "INR"
DEFAULT_CONFIDENCE = "missing"


@dataclass
class MonetaryValue:
    value_original: Optional[float] = None
    unit_original: str = ""
    value_crore: Optional[float] = None
    currency: str = DEFAULT_CURRENCY
    source_year: str = ""
    source_page: Optional[int] = None
    source_artifact: str = ""
    confidence: str = DEFAULT_CONFIDENCE
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value_original": self.value_original,
            "unit_original": self.unit_original,
            "value_crore": self.value_crore,
            "currency": self.currency,
            "source_year": self.source_year,
            "source_page": self.source_page,
            "source_artifact": self.source_artifact,
            "confidence": self.confidence,
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "MonetaryValue":
        return cls(
            value_original=payload.get("value_original"),
            unit_original=payload.get("unit_original", ""),
            value_crore=payload.get("value_crore"),
            currency=payload.get("currency", DEFAULT_CURRENCY),
            source_year=payload.get("source_year", ""),
            source_page=payload.get("source_page"),
            source_artifact=payload.get("source_artifact", ""),
            confidence=payload.get("confidence", DEFAULT_CONFIDENCE),
            notes=[str(item) for item in payload.get("notes", [])],
        )


@dataclass
class NumericValue:
    value: Optional[float] = None
    unit: str = ""
    source_year: str = ""
    source_page: Optional[int] = None
    source_artifact: str = ""
    confidence: str = DEFAULT_CONFIDENCE
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "unit": self.unit,
            "source_year": self.source_year,
            "source_page": self.source_page,
            "source_artifact": self.source_artifact,
            "confidence": self.confidence,
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "NumericValue":
        return cls(
            value=payload.get("value"),
            unit=payload.get("unit", ""),
            source_year=payload.get("source_year", ""),
            source_page=payload.get("source_page"),
            source_artifact=payload.get("source_artifact", ""),
            confidence=payload.get("confidence", DEFAULT_CONFIDENCE),
            notes=[str(item) for item in payload.get("notes", [])],
        )


@dataclass
class CorporateActionValue:
    occurred: Optional[bool] = None
    ratio: str = ""
    amount: MonetaryValue = field(default_factory=MonetaryValue)
    source_year: str = ""
    source_page: Optional[int] = None
    source_artifact: str = ""
    confidence: str = DEFAULT_CONFIDENCE
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "occurred": self.occurred,
            "ratio": self.ratio,
            "amount": self.amount.to_dict(),
            "source_year": self.source_year,
            "source_page": self.source_page,
            "source_artifact": self.source_artifact,
            "confidence": self.confidence,
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "CorporateActionValue":
        return cls(
            occurred=payload.get("occurred"),
            ratio=payload.get("ratio", ""),
            amount=MonetaryValue.from_dict(payload.get("amount", {})),
            source_year=payload.get("source_year", ""),
            source_page=payload.get("source_page"),
            source_artifact=payload.get("source_artifact", ""),
            confidence=payload.get("confidence", DEFAULT_CONFIDENCE),
            notes=[str(item) for item in payload.get("notes", [])],
        )


def _money_field() -> MonetaryValue:
    return MonetaryValue()


def _numeric_field() -> NumericValue:
    return NumericValue()


def _corporate_action_field() -> CorporateActionValue:
    return CorporateActionValue()


@dataclass
class ProfitAndLoss:
    revenue: MonetaryValue = field(default_factory=_money_field)
    other_income: MonetaryValue = field(default_factory=_money_field)
    total_income: MonetaryValue = field(default_factory=_money_field)
    cost_of_materials: MonetaryValue = field(default_factory=_money_field)
    employee_cost: MonetaryValue = field(default_factory=_money_field)
    other_expenses: MonetaryValue = field(default_factory=_money_field)
    ebitda: MonetaryValue = field(default_factory=_money_field)
    depreciation: MonetaryValue = field(default_factory=_money_field)
    ebit: MonetaryValue = field(default_factory=_money_field)
    finance_cost: MonetaryValue = field(default_factory=_money_field)
    pbt: MonetaryValue = field(default_factory=_money_field)
    tax: MonetaryValue = field(default_factory=_money_field)
    pat: MonetaryValue = field(default_factory=_money_field)
    exceptional_items: MonetaryValue = field(default_factory=_money_field)
    eps_basic: MonetaryValue = field(default_factory=_money_field)
    eps_diluted: MonetaryValue = field(default_factory=_money_field)

    def to_dict(self) -> Dict[str, Any]:
        return {key: getattr(self, key).to_dict() for key in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ProfitAndLoss":
        return cls(**{key: MonetaryValue.from_dict(payload.get(key, {})) for key in cls.__dataclass_fields__})


@dataclass
class BalanceSheet:
    equity_share_capital: MonetaryValue = field(default_factory=_money_field)
    reserves: MonetaryValue = field(default_factory=_money_field)
    net_worth: MonetaryValue = field(default_factory=_money_field)
    total_debt: MonetaryValue = field(default_factory=_money_field)
    short_term_debt: MonetaryValue = field(default_factory=_money_field)
    long_term_debt: MonetaryValue = field(default_factory=_money_field)
    cash_and_equivalents: MonetaryValue = field(default_factory=_money_field)
    investments: MonetaryValue = field(default_factory=_money_field)
    inventories: MonetaryValue = field(default_factory=_money_field)
    receivables: MonetaryValue = field(default_factory=_money_field)
    payables: MonetaryValue = field(default_factory=_money_field)
    fixed_assets: MonetaryValue = field(default_factory=_money_field)
    cwip: MonetaryValue = field(default_factory=_money_field)
    total_assets: MonetaryValue = field(default_factory=_money_field)
    total_liabilities: MonetaryValue = field(default_factory=_money_field)

    def to_dict(self) -> Dict[str, Any]:
        return {key: getattr(self, key).to_dict() for key in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "BalanceSheet":
        return cls(**{key: MonetaryValue.from_dict(payload.get(key, {})) for key in cls.__dataclass_fields__})


@dataclass
class CashFlow:
    cfo: MonetaryValue = field(default_factory=_money_field)
    cfi: MonetaryValue = field(default_factory=_money_field)
    cff: MonetaryValue = field(default_factory=_money_field)
    capex: MonetaryValue = field(default_factory=_money_field)
    fcf: MonetaryValue = field(default_factory=_money_field)
    dividends_paid: MonetaryValue = field(default_factory=_money_field)
    interest_paid: MonetaryValue = field(default_factory=_money_field)
    tax_paid: MonetaryValue = field(default_factory=_money_field)

    def to_dict(self) -> Dict[str, Any]:
        return {key: getattr(self, key).to_dict() for key in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "CashFlow":
        return cls(**{key: MonetaryValue.from_dict(payload.get(key, {})) for key in cls.__dataclass_fields__})


@dataclass
class ShareData:
    face_value: MonetaryValue = field(default_factory=_money_field)
    shares_outstanding: NumericValue = field(default_factory=_numeric_field)
    weighted_avg_shares: NumericValue = field(default_factory=_numeric_field)
    diluted_shares: NumericValue = field(default_factory=_numeric_field)
    book_value_per_share: MonetaryValue = field(default_factory=_money_field)
    tangible_book_value_per_share: MonetaryValue = field(default_factory=_money_field)

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for key in self.__dataclass_fields__:
            result[key] = getattr(self, key).to_dict()
        return result

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ShareData":
        return cls(
            face_value=MonetaryValue.from_dict(payload.get("face_value", {})),
            shares_outstanding=NumericValue.from_dict(payload.get("shares_outstanding", {})),
            weighted_avg_shares=NumericValue.from_dict(payload.get("weighted_avg_shares", {})),
            diluted_shares=NumericValue.from_dict(payload.get("diluted_shares", {})),
            book_value_per_share=MonetaryValue.from_dict(payload.get("book_value_per_share", {})),
            tangible_book_value_per_share=MonetaryValue.from_dict(payload.get("tangible_book_value_per_share", {})),
        )


@dataclass
class CorporateActions:
    dividend: CorporateActionValue = field(default_factory=_corporate_action_field)
    bonus: CorporateActionValue = field(default_factory=_corporate_action_field)
    split: CorporateActionValue = field(default_factory=_corporate_action_field)
    buyback: CorporateActionValue = field(default_factory=_corporate_action_field)
    rights_issue: CorporateActionValue = field(default_factory=_corporate_action_field)
    qip: CorporateActionValue = field(default_factory=_corporate_action_field)
    preferential_issue: CorporateActionValue = field(default_factory=_corporate_action_field)
    merger: CorporateActionValue = field(default_factory=_corporate_action_field)
    demerger: CorporateActionValue = field(default_factory=_corporate_action_field)

    def to_dict(self) -> Dict[str, Any]:
        return {key: getattr(self, key).to_dict() for key in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "CorporateActions":
        return cls(**{key: CorporateActionValue.from_dict(payload.get(key, {})) for key in cls.__dataclass_fields__})


@dataclass
class ShareholdingPattern:
    promoter_holding: NumericValue = field(default_factory=_numeric_field)
    pledged_promoter_holding: NumericValue = field(default_factory=_numeric_field)
    fii_holding: NumericValue = field(default_factory=_numeric_field)
    dii_holding: NumericValue = field(default_factory=_numeric_field)
    mutual_fund_holding: NumericValue = field(default_factory=_numeric_field)
    public_holding: NumericValue = field(default_factory=_numeric_field)
    others: NumericValue = field(default_factory=_numeric_field)

    def to_dict(self) -> Dict[str, Any]:
        return {key: getattr(self, key).to_dict() for key in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ShareholdingPattern":
        return cls(**{key: NumericValue.from_dict(payload.get(key, {})) for key in cls.__dataclass_fields__})


@dataclass
class FinancialStatements:
    schema_version: str = FINANCIAL_SCHEMA_VERSION
    profit_and_loss: ProfitAndLoss = field(default_factory=ProfitAndLoss)
    balance_sheet: BalanceSheet = field(default_factory=BalanceSheet)
    cash_flow: CashFlow = field(default_factory=CashFlow)
    share_data: ShareData = field(default_factory=ShareData)
    corporate_actions: CorporateActions = field(default_factory=CorporateActions)
    shareholding_pattern: ShareholdingPattern = field(default_factory=ShareholdingPattern)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profit_and_loss": self.profit_and_loss.to_dict(),
            "balance_sheet": self.balance_sheet.to_dict(),
            "cash_flow": self.cash_flow.to_dict(),
            "share_data": self.share_data.to_dict(),
            "corporate_actions": self.corporate_actions.to_dict(),
            "shareholding_pattern": self.shareholding_pattern.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "FinancialStatements":
        return cls(
            schema_version=payload.get("schema_version", FINANCIAL_SCHEMA_VERSION),
            profit_and_loss=ProfitAndLoss.from_dict(payload.get("profit_and_loss", {})),
            balance_sheet=BalanceSheet.from_dict(payload.get("balance_sheet", {})),
            cash_flow=CashFlow.from_dict(payload.get("cash_flow", {})),
            share_data=ShareData.from_dict(payload.get("share_data", {})),
            corporate_actions=CorporateActions.from_dict(payload.get("corporate_actions", {})),
            shareholding_pattern=ShareholdingPattern.from_dict(payload.get("shareholding_pattern", {})),
        )


def create_empty_financial_statements() -> FinancialStatements:
    return FinancialStatements()
