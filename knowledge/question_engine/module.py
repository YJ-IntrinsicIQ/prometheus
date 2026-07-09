from __future__ import annotations

from .constants import (
    MODULE_CAPITAL_ALLOCATION,
    MODULE_COMPLIANCE_INFRASTRUCTURE,
    MODULE_LIBRARY_ECONOMICS,
    MODULE_PLATFORM_DEPENDENCY,
    MODULE_PLATFORM_ECONOMICS,
    MODULE_TECHNOLOGY,
    OUTPUT_STRUCTURED,
    OUTPUT_SUMMARY,
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_MEDIUM,
)
from .schema import Question, QuestionModule


# Keep this file limited to reusable business-question families.
# New modules should represent cross-company archetypes such as capital allocation,
# platform economics, or compliance infrastructure, not a single company's product line.

def capital_allocation_module() -> QuestionModule:
    module_id = MODULE_CAPITAL_ALLOCATION

    return QuestionModule(
        module_id=module_id,
        module_name="Capital Allocation",
        description=(
            "Questions that test how management deploys capital, "
            "funds growth, and balances reinvestment with shareholder returns."
        ),
        questions=[
            Question(
                id="capital_allocation.major_decisions",
                module=module_id,
                priority=PRIORITY_CRITICAL,
                category="capital_deployment",
                question="What major capital allocation decisions has management made?",
                expected_entity_types=["Plant", "Factory", "Subsidiary", "Project"],
                expected_event_types=["Expansion", "Acquisition", "Buyback", "Dividend"],
                output_type=OUTPUT_STRUCTURED,
            ),
            Question(
                id="capital_allocation.growth_capex",
                module=module_id,
                priority=PRIORITY_HIGH,
                category="growth_investment",
                question="Where is the company investing growth capital, and what strategic objective does it serve?",
                expected_entity_types=["Plant", "Product", "Technology", "Geography"],
                expected_event_types=["Capacity Increase", "New Facility", "Product Launch"],
                output_type=OUTPUT_STRUCTURED,
            ),
            Question(
                id="capital_allocation.funding_sources",
                module=module_id,
                priority=PRIORITY_HIGH,
                category="financing",
                question="How are major investments funded, and does funding increase financial risk?",
                expected_entity_types=["Debt", "Equity", "Cash", "Promoter"],
                expected_event_types=["Debt Raise", "Equity Issuance", "Loan Conversion"],
                output_type=OUTPUT_STRUCTURED,
            ),
            Question(
                id="capital_allocation.return_discipline",
                module=module_id,
                priority=PRIORITY_MEDIUM,
                category="returns",
                question="Does management explain expected returns or payback periods for major capital projects?",
                expected_entity_types=["Project", "Plant", "Investment"],
                expected_event_types=["Capex Approval", "Commissioning"],
                output_type=OUTPUT_SUMMARY,
            ),
            Question(
                id="capital_allocation.shareholder_returns",
                module=module_id,
                priority=PRIORITY_MEDIUM,
                category="shareholder_returns",
                question="Has management returned capital through dividends, buybacks, or other shareholder distributions?",
                expected_entity_types=["Dividend", "Buyback", "Shareholder"],
                expected_event_types=["Dividend", "Buyback", "Distribution"],
                output_type=OUTPUT_STRUCTURED,
            ),
            Question(
                id="capital_allocation.capital_tradeoffs",
                module=module_id,
                priority=PRIORITY_MEDIUM,
                category="capital_tradeoffs",
                question="What tradeoffs does management appear to be making between growth, balance sheet strength, and shareholder returns?",
                expected_entity_types=["Debt", "Cash", "Project", "Shareholder"],
                expected_event_types=["Expansion", "Debt Repayment", "Dividend"],
                output_type=OUTPUT_SUMMARY,
            ),
        ],
    )


def technology_module() -> QuestionModule:
    module_id = MODULE_TECHNOLOGY

    return QuestionModule(
        module_id=module_id,
        module_name="Technology",
        description=(
            "Questions that examine technology capability, R&D intensity, "
            "automation, intellectual property, and technical differentiation."
        ),
        questions=[
            Question(
                id="technology.core_capabilities",
                module=module_id,
                priority=PRIORITY_CRITICAL,
                category="technology_capability",
                question="What core technologies does the company claim as important to its business model?",
                expected_entity_types=["Technology", "Product", "Process", "Platform"],
                expected_event_types=["Technology Adoption", "Product Development"],
                output_type=OUTPUT_STRUCTURED,
            ),
            Question(
                id="technology.r_and_d_focus",
                module=module_id,
                priority=PRIORITY_HIGH,
                category="research_and_development",
                question="What R&D priorities, programs, or collaborations does management describe?",
                expected_entity_types=["Research Program", "Institution", "Product", "Patent"],
                expected_event_types=["R&D Expansion", "Collaboration", "Product Development"],
                output_type=OUTPUT_STRUCTURED,
            ),
            Question(
                id="technology.automation",
                module=module_id,
                priority=PRIORITY_HIGH,
                category="automation",
                question="How is the company using automation, software, or data systems to improve operations?",
                expected_entity_types=["Software", "Automation System", "Factory", "Process"],
                expected_event_types=["Automation", "Digital Transformation", "Process Improvement"],
                output_type=OUTPUT_STRUCTURED,
            ),
            Question(
                id="technology.differentiation",
                module=module_id,
                priority=PRIORITY_HIGH,
                category="differentiation",
                question="Does technology create measurable differentiation in cost, quality, speed, or customer value?",
                expected_entity_types=["Technology", "Customer", "Product", "Process"],
                expected_event_types=["Product Launch", "Process Improvement", "Customer Win"],
                output_type=OUTPUT_SUMMARY,
            ),
            Question(
                id="technology.dependency_risk",
                module=module_id,
                priority=PRIORITY_MEDIUM,
                category="technology_risk",
                question="Is the company dependent on external technology providers, licenses, or hard-to-replace technical talent?",
                expected_entity_types=["Vendor", "License", "Employee", "Technology"],
                expected_event_types=["Licensing", "Partnership", "Technology Change"],
                output_type=OUTPUT_STRUCTURED,
            ),
            Question(
                id="technology.commercialization",
                module=module_id,
                priority=PRIORITY_MEDIUM,
                category="commercialization",
                question="Has management converted technology investments into commercial products, capacity, or revenue opportunities?",
                expected_entity_types=["Product", "Customer", "Plant", "Technology"],
                expected_event_types=["Commercial Launch", "Capacity Increase", "Customer Win"],
                output_type=OUTPUT_STRUCTURED,
            ),
        ],
    )


def library_economics_module() -> QuestionModule:
    module_id = MODULE_LIBRARY_ECONOMICS

    return QuestionModule(
        module_id=module_id,
        module_name="Library Economics",
        description=(
            "Questions that examine how a business monetizes owned or licensed "
            "content, catalogue, or other reusable intellectual-property assets."
        ),
        questions=[
            Question(
                id="library_economics.monetization_base",
                module=module_id,
                priority=PRIORITY_CRITICAL,
                category="library_monetization",
                question="What assets or rights form the monetizable library, and how does management say they generate revenue?",
                expected_entity_types=["Content Library", "License", "Catalog", "Product"],
                expected_event_types=["Licensing", "Distribution", "Rights Deal"],
                output_type=OUTPUT_STRUCTURED,
            ),
            Question(
                id="library_economics.recurring_revenue",
                module=module_id,
                priority=PRIORITY_HIGH,
                category="recurring_revenue",
                question="How recurring is revenue from the existing library or rights base, and what channels drive that recurrence?",
                expected_entity_types=["Revenue Stream", "Platform", "Customer", "License"],
                expected_event_types=["Renewal", "Licensing", "Royalty Collection"],
                output_type=OUTPUT_STRUCTURED,
            ),
            Question(
                id="library_economics.refresh_strategy",
                module=module_id,
                priority=PRIORITY_HIGH,
                category="library_refresh",
                question="How does management refresh, expand, or improve the monetizable library over time?",
                expected_entity_types=["Catalog", "Creator", "Content Library", "Product"],
                expected_event_types=["Content Release", "Acquisition", "Partnership"],
                output_type=OUTPUT_STRUCTURED,
            ),
            Question(
                id="library_economics.channel_mix",
                module=module_id,
                priority=PRIORITY_MEDIUM,
                category="channel_mix",
                question="What monetization channels matter most for the library, and how diversified are they?",
                expected_entity_types=["Platform", "License", "Customer", "Channel"],
                expected_event_types=["Distribution", "Licensing", "Revenue Share Change"],
                output_type=OUTPUT_SUMMARY,
            ),
        ],
    )


def platform_dependency_module() -> QuestionModule:
    module_id = MODULE_PLATFORM_DEPENDENCY

    return QuestionModule(
        module_id=module_id,
        module_name="Platform Dependency",
        description=(
            "Questions that examine third-party distribution dependence, owned-channel "
            "reach, enforcement risk, and digital monetization concentration."
        ),
        questions=[
            Question(
                id="platform_dependency.concentration",
                module=module_id,
                priority=PRIORITY_CRITICAL,
                category="platform_concentration",
                question="How dependent is the business on third-party platforms, marketplaces, or distributors for monetization and reach?",
                expected_entity_types=["Platform", "Distributor", "Channel", "Customer"],
                expected_event_types=["Distribution Agreement", "Platform Change", "Policy Change"],
                output_type=OUTPUT_STRUCTURED,
            ),
            Question(
                id="platform_dependency.owned_audience",
                module=module_id,
                priority=PRIORITY_HIGH,
                category="owned_audience",
                question="How important is owned audience reach or direct channel access versus third-party platform reach?",
                expected_entity_types=["Audience", "Platform", "Channel", "Customer"],
                expected_event_types=["Audience Growth", "Channel Launch", "Distribution Expansion"],
                output_type=OUTPUT_STRUCTURED,
            ),
            Question(
                id="platform_dependency.enforcement_risk",
                module=module_id,
                priority=PRIORITY_HIGH,
                category="enforcement_risk",
                question="What risks does management describe around rights enforcement, piracy, leakage, or platform compliance?",
                expected_entity_types=["Platform", "License", "Content", "Regulator"],
                expected_event_types=["Piracy Incident", "Takedown", "Compliance Change"],
                output_type=OUTPUT_STRUCTURED,
            ),
            Question(
                id="platform_dependency.unit_economics",
                module=module_id,
                priority=PRIORITY_MEDIUM,
                category="digital_unit_economics",
                question="Does management explain the economics of platform-based monetization such as revenue share, advertising, subscriptions, or licensing yield?",
                expected_entity_types=["Platform", "Revenue Stream", "License", "Customer"],
                expected_event_types=["Revenue Share Change", "Licensing", "Advertising Monetization"],
                output_type=OUTPUT_SUMMARY,
            ),
        ],
    )


def platform_economics_module() -> QuestionModule:
    module_id = MODULE_PLATFORM_ECONOMICS

    return QuestionModule(
        module_id=module_id,
        module_name="Platform Economics",
        description=(
            "Questions that examine usage scale, deployment economics, customer "
            "embeddedness, and partner/channel expansion for enterprise platforms."
        ),
        questions=[
            Question(
                id="platform_economics.usage_scale",
                module=module_id,
                priority=PRIORITY_CRITICAL,
                category="usage_scale",
                question="What evidence does management provide about platform usage scale, throughput, customer base, or deployment volume?",
                expected_entity_types=["Platform", "Customer", "Product", "Channel"],
                expected_event_types=["Customer Expansion", "Platform Launch", "Usage Growth"],
                output_type=OUTPUT_STRUCTURED,
            ),
            Question(
                id="platform_economics.customer_embeddedness",
                module=module_id,
                priority=PRIORITY_HIGH,
                category="customer_embeddedness",
                question="How embedded is the platform in customer workflows, and what signals suggest switching costs, retention, or repeat usage?",
                expected_entity_types=["Customer", "Workflow", "Platform", "Partner"],
                expected_event_types=["Renewal", "Deployment", "Integration"],
                output_type=OUTPUT_STRUCTURED,
            ),
            Question(
                id="platform_economics.partner_expansion",
                module=module_id,
                priority=PRIORITY_HIGH,
                category="partner_expansion",
                question="How does the company expand distribution through ecosystem, telco, channel, or partner integrations?",
                expected_entity_types=["Partner", "Operator", "Platform", "Channel"],
                expected_event_types=["Partnership", "Distribution Expansion", "Regional Expansion"],
                output_type=OUTPUT_STRUCTURED,
            ),
            Question(
                id="platform_economics.deployment_efficiency",
                module=module_id,
                priority=PRIORITY_MEDIUM,
                category="deployment_economics",
                question="Does management describe deployment automation, observability, reliability, or operational leverage that improves platform economics?",
                expected_entity_types=["Platform", "Process", "Technology", "Customer"],
                expected_event_types=["Automation", "Process Improvement", "Deployment"],
                output_type=OUTPUT_SUMMARY,
            ),
        ],
    )


def compliance_infrastructure_module() -> QuestionModule:
    module_id = MODULE_COMPLIANCE_INFRASTRUCTURE

    return QuestionModule(
        module_id=module_id,
        module_name="Compliance Infrastructure",
        description=(
            "Questions that examine compliance-by-design, trust-layer differentiation, "
            "fraud prevention, and regulatory embeddedness in software platforms."
        ),
        questions=[
            Question(
                id="compliance_infrastructure.core_controls",
                module=module_id,
                priority=PRIORITY_CRITICAL,
                category="compliance_controls",
                question="What compliance, trust, anti-fraud, or anti-abuse capabilities are embedded in the core product offering?",
                expected_entity_types=["Platform", "Product", "Regulator", "Customer"],
                expected_event_types=["Compliance Change", "Product Launch", "Security Enhancement"],
                output_type=OUTPUT_STRUCTURED,
            ),
            Question(
                id="compliance_infrastructure.commercial_value",
                module=module_id,
                priority=PRIORITY_HIGH,
                category="commercial_value",
                question="How does management describe compliance or trust capability as a source of customer value, product differentiation, or market access?",
                expected_entity_types=["Customer", "Platform", "Product", "Regulator"],
                expected_event_types=["Customer Win", "Certification", "Partnership"],
                output_type=OUTPUT_STRUCTURED,
            ),
            Question(
                id="compliance_infrastructure.regulatory_dependency",
                module=module_id,
                priority=PRIORITY_HIGH,
                category="regulatory_dependency",
                question="Which regulatory, ecosystem, or operator requirements meaningfully shape product deployment, channel access, or platform adoption?",
                expected_entity_types=["Regulator", "Operator", "Partner", "Platform"],
                expected_event_types=["Compliance Change", "Platform Deployment", "Partnership"],
                output_type=OUTPUT_STRUCTURED,
            ),
            Question(
                id="compliance_infrastructure.abuse_prevention",
                module=module_id,
                priority=PRIORITY_MEDIUM,
                category="abuse_prevention",
                question="What evidence shows the platform reduces spam, phishing, fraud, abuse, or other trust-damaging activity at scale?",
                expected_entity_types=["Platform", "Customer", "Product", "Operator"],
                expected_event_types=["Fraud Prevention", "Security Enhancement", "Usage Growth"],
                output_type=OUTPUT_SUMMARY,
            ),
        ],
    )


def default_modules() -> list[QuestionModule]:
    return [
        capital_allocation_module(),
        technology_module(),
        library_economics_module(),
        platform_dependency_module(),
        platform_economics_module(),
        compliance_infrastructure_module(),
    ]
