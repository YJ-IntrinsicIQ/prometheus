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
        "share_of_profit_associates",
        "share_of_profit_jv",
        "non_controlling_interests",
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
        "other_assets",
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
            "aliases": [
                "revenue from operations", "revenue", "income from operations",
                # Banking schedule aliases (RBI Schedule III - Schedule 13: Interest Earned)
                "interest earned", "interest income", "interest on advances", "interest on loans",
                "interest on investments", "interest on balances with rbi", "interest on deposits with rbi",
                "interest on money at call", "discount on bills", "income from interest",
                "interest discount on advance bills", "income on investments",
            ],
        },
        "other_income": {
            "table_types": ["profit_and_loss", "revenue"],
            "aliases": [
                "other income", "non operating income",
                # Banking schedule aliases (RBI Schedule III - Schedule 14: Other Income)
                "commission exchange and brokerage", "commission, exchange and brokerage",
                "profit on sale of investments", "profit on revaluation of investments",
                "profit on sale of land buildings and other assets", "profit on exchange transactions",
                "miscellaneous income", "rent received", "dividend income",
            ],
        },
        "total_income": {
            "table_types": ["profit_and_loss", "revenue"],
            "aliases": ["total income", "total income (i+ii)", "total of interest earned and other income"],
        },
        "cost_of_materials": {
            "table_types": ["profit_and_loss", "tax"],
            "aliases": [
                "cost of materials consumed",
                "material cost",
                "materials consumed",
                "consumption of materials stores and spare parts",
                "consumption of materials, stores and spare parts",
            ],
        },
        "employee_cost": {
            "table_types": ["profit_and_loss"],
            "aliases": [
                "employee benefits expense", "employee cost", "staff cost", "personnel cost",
                # Banking schedule aliases (RBI Schedule III - Schedule 16: Operating Expenses)
                "payments to and provision for employees", "payments to employees",
                "payments to and provision for employee", "payment to and provision for employees",
                "salaries and allowances", "contribution to provident fund", "staff welfare",
            ],
        },
        "other_expenses": {
            "table_types": ["profit_and_loss"],
            "aliases": [
                "other expenses", "operating expenses",
                # Banking schedule aliases (RBI Schedule III - Schedule 16: Operating Expenses)
                "rent taxes and lighting", "rent, taxes and lighting",
                "printing and stationery", "printing, stationery",
                "advertisement and publicity", "advertisement",
                "depreciation on banks property", "depreciation on bank's property",
                "directors fees", "directors' fees", "auditors fees", "auditors' fees",
                "law charges", "legal expenses",
                "postage telegrams and telephone", "postage, telegrams and telephone",
                "repairs and maintenance", "repairs",
                "insurance", "other expenditure", "miscellaneous expenses",
                "operating expenses (i to x)", "total operating expenses",
            ],
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
            "aliases": [
                "finance cost", "finance costs", "interest expense",
                # Banking schedule aliases (RBI Schedule III - Schedule 15: Interest Expended)
                "interest expended", "interest expense", "interest paid",
                "interest on deposits", "interest on borrowings", "interest on rbi borrowings",
                "interest on inter-bank borrowings", "discount on bills", "other interest",
            ],
        },
        "pbt": {
            "table_types": ["profit_and_loss", "cash_flow"],
            "aliases": [
                "profit before tax",
                "profit before taxation",
                "net profit before tax",
                "profit before tax after exceptional items",
                "profit before tax (after exceptional items)",
                "profit before tax (v-vi)",
                "profit before tax (vi-vii)",
                "profit before tax after exceptional item",
                "profit before tax (after exceptional items)",
                "pbt",
            ],
        },
        "tax": {
            "table_types": ["profit_and_loss", "tax", "balance_sheet", "cash_flow"],
            "aliases": ["total tax expense", "tax expense", "tax expenses", "income tax expense", "tax", "tax adjustment"],
        },
        "pat": {
            "table_types": ["profit_and_loss", "balance_sheet", "cash_flow"],
            "aliases": [
                "profit for the year",
                "profit for the year attributable to owners of the company",
                "profit attributable to owners of the company",
                "profit after tax",
                "profit after taxation",
                "net profit after taxation",
                "net profit 5 6 8 9",
                "pat",
                "profit for the period",
            ],
        },
        "share_of_profit_associates": {
            "table_types": ["profit_and_loss"],
            "aliases": [
                "share of profit/(loss) of associates (net of tax)",
                "share of profit of associates (net of tax)",
                "share of profit/(loss) of associates",
                "share of profit of associates",
                "share in profit of associates",
                "profit/(loss) from associates",
                "share of profit / (loss) of associates",
            ],
        },
        "share_of_profit_jv": {
            "table_types": ["profit_and_loss"],
            "aliases": [
                "share of profit/(loss) of joint venture (net of tax)",
                "share of profit of joint venture (net of tax)",
                "share of profit/(loss) of joint venture",
                "share of profit of joint venture",
                "share in profit of joint venture",
                "profit/(loss) from joint ventures",
            ],
        },
        "non_controlling_interests": {
            "table_types": ["profit_and_loss"],
            "aliases": [
                "non-controlling interests",
                "non controlling interests",
                "minority interest",
                "minority interests",
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
            "aliases": [
                "trade receivables",
                "receivables",
                "accounts receivable",
                # Banking schedule aliases (RBI Schedule III - Schedule 9 Advances)
                "advances",
                "advances (net of provisions)",
                "bills purchased and discounted",
                "cash credits overdrafts and loans repayable on demand",
                "term loans",
                "secured by tangible assets",
                "covered by bank government guarantees",
                "unsecured",
            ],
        },
        "payables": {
            "table_types": ["balance_sheet", "borrowings", "dividend"],
            "aliases": [
                "trade payables",
                "trade payable",
                "total trade payables",
                "total trade payable",
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
        "other_assets": {
            "table_types": ["balance_sheet"],
            "aliases": [
                "other assets",
                # Banking schedule aliases (RBI Schedule III - Schedule 11)
                "total other assets",
                "inter office adjustment",
                "interest accrued",
                "tax paid in advance",
                "stationery and stamps",
                "non-banking assets acquired",
                "deferred tax assets",
                "others",
            ],
            "forbidden": [
                "deposits",
                "term deposits",
                "demand deposits",
                "savings bank deposits",
                "borrowings",
                "liabilities",
                "capital",
                "reserves",
            ],
        },
        "total_assets": {
            "table_types": ["balance_sheet"],
            "aliases": [
                "total assets",
                "total equity and liabilities",
            ],
        },
        "total_liabilities": {
            "table_types": ["balance_sheet"],
            "aliases": [
                "total liabilities",
                # Banking schedule aliases (RBI Schedule III)
                "total liabilities reserves and surplus",
                "total liabilities reserves and surplus b",
                "total i ii iii",
                "total i + ii + iii",
                "total (i + ii + iii)",
            ],
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
                "weighted average number of shares used in computing diluted earnings per share",
                "weighted average number of shares used for diluted earnings per share",
                "weighted average number of shares used in computing basic and diluted earnings per share",
                "weighted average number of shares used for basic and diluted earnings per share",
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
