# Ask IntrinsicIQ backend layer

This package builds the canonical backend output directory for Ask IntrinsicIQ.

Purpose:

- load existing company-memory sources safely
- produce UI-ready public outputs
- keep frontend rendering decoupled from internal company-memory structures

Canonical inputs:

- `company_memory/pcim_v1.json`
- `company_memory/financials/financial_truth_pack.json`
- `company_memory/financials/investor_financial_modules/investor_financial_modules_manifest.json`
- `company_memory/investor_panel/committee_synthesis.json`
- `company_memory/company_memory_index.json`

Canonical outputs:

- `company_research_view.json`
- `business_journey.json`
- `products_services.json`
- `answer_cards.json`
- `financial_visual_summaries.json`
- `uncertainty_map.json`
- `ask_intrinsiciq_manifest.json`
- `ask_intrinsiciq_validation_report.json`

Current implementation status:

- deterministic backend shell plus business journey generator
- deterministic products and services mapper
- deterministic curated question catalog and answer-card generator
- deterministic financial visual summary generator
- deterministic uncertainty and missing-evidence mapper
- writes `business_journey.json`
- writes `products_services.json`
- writes `answer_cards.json`
- writes `financial_visual_summaries.json`
- writes `uncertainty_map.json`
- writes `company_research_view.json` with a referenced journey view
- writes manifest and validation report

Notes:

- no new LLM call is introduced by default
- financial visuals stay compact, chart-ready, and evidence-safe rather than dashboard-like
- uncertainty outputs explain what is missing, why it matters, and what to investigate next
- frontend should consume only the public UI-ready outputs from this package
