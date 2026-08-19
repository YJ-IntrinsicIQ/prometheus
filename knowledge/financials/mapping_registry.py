from __future__ import annotations

from typing import Dict, List


CANONICAL_SECTION_FIELDS: Dict[str, List[str]] = {
    "profit_and_loss": [
        "revenue",
        "other_income",
        "total_income",
        "cost_of_materials",
        "employee_cost",
        "other_expenses",
        "ebitda",
        "depreciation",
        "ebit",
        "finance_cost",
        "pbt",
        "tax",
        "pat",
        "eps_basic",
        "eps_diluted",
    ],
    "balance_sheet": [
        "equity_share_capital",
        "reserves",
        "net_worth",
        "total_debt",
        "short_term_debt",
        "long_term_debt",
        "cash_and_equivalents",
        "investments",
        "inventories",
        "receivables",
        "payables",
        "fixed_assets",
        "cwip",
        "total_assets",
        "total_liabilities",
    ],
    "cash_flow": [
        "cfo",
        "cfi",
        "cff",
        "capex",
        "fcf",
        "dividends_paid",
        "interest_paid",
        "tax_paid",
    ],
    "share_data": [
        "face_value",
        "shares_outstanding",
        "weighted_avg_shares",
        "diluted_shares",
        "book_value_per_share",
    ],
    "corporate_actions": [
        "dividend",
        "split",
        "bonus",
        "buyback",
        "rights_issue",
        "qip",
        "preferential_issue",
    ],
    "shareholding_pattern": [
        "promoter_holding",
        "pledged_promoter_holding",
        "fii_holding",
        "dii_holding",
        "mutual_fund_holding",
        "public_holding",
    ],
}


FIELD_MAPPINGS: Dict[str, Dict[str, Dict[str, object]]] = {
    "profit_and_loss": {
        "revenue": {
            "table_types": ["profit_and_loss", "balance_sheet", "revenue"],
            "aliases": ["revenue from operations", "revenue", "income from operations"],
        },
        "other_income": {
            "table_types": ["profit_and_loss", "revenue"],
            "aliases": ["other income", "non operating income"],
        },
        "total_income": {
            "table_types": ["profit_and_loss", "revenue"],
            "aliases": ["total income"],
        },
        "cost_of_materials": {
            "table_types": ["profit_and_loss"],
            "aliases": ["cost of materials consumed", "material cost", "materials consumed"],
        },
        "employee_cost": {
            "table_types": ["profit_and_loss"],
            "aliases": ["employee benefits expense", "employee cost", "staff cost", "personnel cost"],
        },
        "other_expenses": {
            "table_types": ["profit_and_loss"],
            "aliases": ["other expenses", "operating expenses"],
        },
        "ebitda": {
            "table_types": ["profit_and_loss"],
            "aliases": ["ebitda", "operating profit before depreciation and amortisation"],
        },
        "depreciation": {
            "table_types": ["profit_and_loss", "cash_flow", "fixed_assets"],
            "aliases": ["depreciation and amortization expense", "depreciation", "depreciation and amortisation"],
        },
        "ebit": {
            "table_types": ["profit_and_loss"],
            "aliases": ["ebit", "operating profit"],
        },
        "finance_cost": {
            "table_types": ["profit_and_loss", "cash_flow", "borrowings"],
            "aliases": ["finance cost", "finance costs", "interest expense"],
        },
        "pbt": {
            "table_types": ["profit_and_loss", "cash_flow"],
            "aliases": ["profit before tax", "profit before taxation", "net profit before tax"],
        },
        "tax": {
            "table_types": ["profit_and_loss", "tax", "balance_sheet", "cash_flow"],
            "aliases": ["total tax expense", "tax expense", "tax expenses", "income tax expense", "tax"],
        },
        "pat": {
            "table_types": ["profit_and_loss", "balance_sheet", "cash_flow"],
            "aliases": [
                "profit for the year",
                "profit after tax",
                "profit after taxation",
                "net profit after taxation",
                "net profit 5 6 8 9",
                "pat",
                "profit for the period",
            ],
        },
        "eps_basic": {
            "table_types": ["profit_and_loss", "eps"],
            "aliases": ["basic earnings per share", "basic eps", "basic and diluted"],
        },
        "eps_diluted": {
            "table_types": ["profit_and_loss", "eps"],
            "aliases": ["diluted earnings per share", "diluted eps", "basic and diluted"],
        },
    },
    "balance_sheet": {
        "equity_share_capital": {
            "table_types": ["balance_sheet", "share_capital"],
            "aliases": ["equity share capital", "share capital", "paid up capital", "paid up share capital"],
        },
        "reserves": {
            "table_types": ["balance_sheet", "reserves", "share_capital", "statement_of_changes_in_equity"],
            "aliases": [
                "other equity",
                "reserves and surplus",
                "reserves",
                "total i ii iii iv v",
                "surplus in statement of profit and loss",
                "retained earnings",
                "investment fluctuation reserve",
            ],
        },
        "net_worth": {
            "table_types": ["balance_sheet", "reserves"],
            "aliases": [
                "total equity",
                "net worth",
                "shareholders funds",
                "shareholders' funds",
                "shareholders equity",
                "shareholders' equity",
                "equity attributable to owners",
                "equity attributable to shareholders",
            ],
        },
        "total_debt": {
            "table_types": ["balance_sheet", "borrowings"],
            "aliases": ["total debt", "total borrowings", "borrowings"],
        },
        "short_term_debt": {
            "table_types": ["balance_sheet", "borrowings"],
            "aliases": ["short term borrowings", "current borrowings", "short-term debt"],
        },
        "long_term_debt": {
            "table_types": ["balance_sheet", "borrowings"],
            "aliases": ["long term borrowings", "non-current borrowings", "long-term debt"],
        },
        "cash_and_equivalents": {
            "table_types": ["balance_sheet", "cash_flow"],
            "aliases": ["cash and cash equivalents", "cash equivalents", "cash and bank balances"],
        },
        "investments": {
            "table_types": ["balance_sheet", "cash_flow"],
            "aliases": ["investment", "investments"],
        },
        "inventories": {
            "table_types": ["balance_sheet"],
            "aliases": ["inventories", "inventory"],
        },
        "receivables": {
            "table_types": ["balance_sheet"],
            "aliases": ["trade receivables", "receivables", "accounts receivable"],
        },
        "payables": {
            "table_types": ["balance_sheet"],
            "aliases": [
                "trade payables",
                "total trade payables",
                "accounts payable",
                "supplier payables",
                "dues to suppliers",
                "creditors for goods services",
                "creditors for goods and services",
                "total outstanding dues of micro enterprises and small enterprises",
                "total outstanding dues of creditors other than micro enterprises and small enterprises",
            ],
        },
        "fixed_assets": {
            "table_types": ["balance_sheet", "fixed_assets"],
            "aliases": ["property, plant and equipment", "fixed assets", "property plant and equipment"],
        },
        "cwip": {
            "table_types": ["balance_sheet", "fixed_assets"],
            "aliases": ["capital work in progress", "cwip"],
        },
        "total_assets": {
            "table_types": ["balance_sheet"],
            "aliases": ["total assets"],
        },
        "total_liabilities": {
            "table_types": ["balance_sheet"],
            "aliases": ["total liabilities"],
        },
    },
    "cash_flow": {
        "cfo": {
            "table_types": ["cash_flow"],
            "aliases": ["net cash generated from operating activities", "net cash from operating activities", "operating cash flow"],
        },
        "cfi": {
            "table_types": ["cash_flow"],
            "aliases": ["net cash used in investing activities", "net cash from investing activities"],
        },
        "cff": {
            "table_types": ["cash_flow"],
            "aliases": ["net cash generated from financing activities", "net cash from financing activities", "net cash used in financing activities"],
        },
        "capex": {
            "table_types": ["cash_flow", "fixed_assets"],
            "aliases": [
                "purchase of property, plant and equipment",
                "purchase of property plant and equipment",
                "purchase of ppe",
                "acquisition of property plant and equipment",
                "acquisition of property plant equipment",
                "payment for property plant and equipment",
                "payment for property, plant and equipment",
                "purchase of fixed assets",
                "purchase of intangible assets",
                "capital expenditure",
                "capex",
                "investment in capital work in progress",
                "investment in capital work in progress cash flow",
            ],
        },
        "fcf": {
            "table_types": ["cash_flow"],
            "aliases": ["free cash flow", "fcf"],
        },
        "dividends_paid": {
            "table_types": ["cash_flow", "dividend", "corporate_actions"],
            "aliases": ["dividends paid", "dividend paid"],
        },
        "interest_paid": {
            "table_types": ["cash_flow", "borrowings"],
            "aliases": ["interest paid", "finance cost paid"],
        },
        "tax_paid": {
            "table_types": ["cash_flow", "tax"],
            "aliases": [
                "income taxes paid", "taxes paid", "tax paid",
                "direct taxes paid net of funds",
                "tax adjustment", "tax adjustments",
            ],
        },
    },
    "share_data": {
        "face_value": {
            "table_types": ["share_capital", "eps"],
            "aliases": [
                "face value",
                "nominal value",
                "nominal value of equity shares",
                "face value of equity shares",
                "equity shares of rs",
                "equity shares of re",
            ],
        },
        "shares_outstanding": {
            "table_types": ["share_capital", "eps"],
            "aliases": [
                "number of equity shares",
                "number of shares outstanding",
                "number of equity shares outstanding",
                "shares outstanding",
                "equity shares outstanding",
                "outstanding equity shares",
                "issued equity shares",
                "subscribed equity shares",
                "paid up equity shares",
                "paid-up equity shares",
                "issued subscribed and paid up equity shares",
                "issued subscribed and paid-up equity shares",
                "issued subscribed paid up equity shares",
                "issued subscribed paid-up equity shares",
                "issued subscribed and fully paid up equity shares",
                "issued subscribed and fully paid-up equity shares",
                "equity shares outstanding at end of year",
            ],
        },
        "weighted_avg_shares": {
            "table_types": ["eps"],
            "aliases": [
                "weighted average number of equity shares",
                "weighted average shares outstanding",
                "weighted average shares",
                "weighted average number of shares used in eps calculation",
                "weighted average number of shares used for eps",
            ],
        },
        "diluted_shares": {
            "table_types": ["eps"],
            "aliases": [
                "weighted average number of diluted equity shares",
                "diluted weighted average number of equity shares",
                "diluted weighted average shares",
                "number of shares used for diluted eps",
                "number of shares used in diluted eps calculation",
            ],
        },
        "book_value_per_share": {
            "table_types": ["share_capital", "reserves"],
            "aliases": ["book value per share", "net asset value per share"],
        },
    },
    "corporate_actions": {
        "dividend": {
            "table_types": ["dividend", "corporate_actions", "cash_flow"],
            "aliases": ["dividend", "dividend paid", "final dividend", "interim dividend"],
        },
        "split": {
            "table_types": ["corporate_actions", "share_capital"],
            "aliases": ["stock split", "split of shares", "share split"],
        },
        "bonus": {
            "table_types": ["corporate_actions", "share_capital"],
            "aliases": ["bonus issue", "bonus shares"],
        },
        "buyback": {
            "table_types": ["corporate_actions", "share_capital"],
            "aliases": ["buyback", "share buyback"],
        },
        "rights_issue": {
            "table_types": ["corporate_actions", "share_capital"],
            "aliases": ["rights issue"],
        },
        "qip": {
            "table_types": ["corporate_actions", "share_capital"],
            "aliases": ["qualified institutional placement", "qip"],
        },
        "preferential_issue": {
            "table_types": ["corporate_actions", "share_capital"],
            "aliases": ["preferential issue"],
        },
    },
    "shareholding_pattern": {
        "promoter_holding": {
            "table_types": ["shareholding_pattern"],
            "aliases": ["promoter holding", "promoter shareholding"],
        },
        "pledged_promoter_holding": {
            "table_types": ["shareholding_pattern"],
            "aliases": ["pledged promoter holding", "promoter pledged holding"],
        },
        "fii_holding": {
            "table_types": ["shareholding_pattern"],
            "aliases": ["fii holding", "foreign institutional investors", "foreign investors"],
        },
        "dii_holding": {
            "table_types": ["shareholding_pattern"],
            "aliases": ["dii holding", "domestic institutional investors"],
        },
        "mutual_fund_holding": {
            "table_types": ["shareholding_pattern"],
            "aliases": ["mutual fund holding", "mutual funds"],
        },
        "public_holding": {
            "table_types": ["shareholding_pattern"],
            "aliases": ["public holding", "public shareholding"],
        },
    },
}


SPECIAL_MULTI_FIELD_ALIASES = {
    "basic and diluted": ["eps_basic", "eps_diluted"],
}
