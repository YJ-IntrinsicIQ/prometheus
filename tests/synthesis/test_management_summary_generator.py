from synthesis import management_summary_generator as generator


def test_ip_library_summary_prioritizes_business_native_signals():
    profile = {
        "projects": [
            {
                "project_name": "Project 1",
                "description": "Capital work-in-progress (CWIP) recorded; amount INR 1.53 Lakhs.",
                "category": "operational_initiative",
            }
        ],
        "promises": [
            {
                "promise": "To create, acquire and deliver quality music having high catalogue value to a wide range of audiences",
                "category": "strategic objective",
            }
        ],
        "initiatives": [
            {
                "initiative": "Use of glass/steel bottles at offices to reduce single-use plastic bottles",
                "category": "Plastic reduction / Resource efficiency",
                "benefit": "Reduced consumption of single-use plastic bottles",
            },
            {
                "initiative": "Built and maintained a music library of over 30,000 songs across genres and major languages",
                "category": "Content Library",
                "benefit": "Large reusable library for long-tail monetization",
            },
            {
                "initiative": "Released 733 new songs in the financial year 2023-24",
                "category": "Content Release",
                "benefit": "Refreshes the monetizable catalogue",
            },
            {
                "initiative": "Licensed and exploited audio-visual content digitally in India and overseas through licensing on various platforms",
                "category": "Digital Distribution / Licensing",
                "benefit": "Expands rights monetization and platform reach",
            },
        ],
        "capital_allocation": [
            {
                "action": "Buyback of equity shares",
                "category": "Buyback",
            }
        ],
    }

    summary = generator.build_summary(
        profile,
        business_context={"business_dnas": ["IP Library", "Platform Monetization", "Export"]},
    )

    assert summary["major_projects"] == []
    assert summary["management_focus_areas"] == [
        "Digital Distribution / Licensing",
        "Content Release",
        "Content Library",
    ]
    assert summary["key_initiatives"] == [
        "Licensed and exploited audio-visual content digitally in India and overseas through licensing on various platforms",
        "Released 733 new songs in the financial year 2023-24",
        "Built and maintained a music library of over 30,000 songs across genres and major languages",
    ]


def test_manufacturing_summary_keeps_core_operational_items():
    profile = {
        "projects": [
            {
                "project_name": "New wafer fabrication line",
                "description": "Expansion of semiconductor production capacity",
                "category": "capacity expansion",
            }
        ],
        "promises": [],
        "initiatives": [
            {
                "initiative": "Installed advanced automation for production",
                "category": "Advanced Manufacturing",
                "benefit": "Improves production quality and efficiency",
            }
        ],
        "capital_allocation": [],
    }

    summary = generator.build_summary(
        profile,
        business_context={"business_dnas": ["Manufacturing", "Semiconductor"]},
    )

    assert summary["major_projects"] == ["New wafer fabrication line"]
    assert summary["key_initiatives"] == ["Installed advanced automation for production"]


def test_materiality_scoring_uses_generic_dimensions_not_product_names():
    positive_score, positive_dimensions = generator._score_item_for_context(
        {
            "category": "Security & Compliance",
            "benefit": "Improves trust and reduces fraud",
            "description": "API-first communications platform with active-active reliability and operator partnerships.",
        },
        (
            "API-first communications platform with active-active reliability, "
            "customer deployments, operator partnerships, and embedded anti-fraud controls."
        ),
        {"Enterprise Platform", "Compliance Infrastructure"},
        "initiative",
    )
    negative_score, negative_dimensions = generator._score_item_for_context(
        {
            "category": "Community / Infrastructure",
            "benefit": "CSR support",
            "description": "School support, water conservation, and employee commuting facilities.",
        },
        "School support, water conservation, employee commuting buses, and landscaping around offices.",
        {"Enterprise Platform", "Compliance Infrastructure"},
        "initiative",
    )

    assert positive_score > negative_score
    assert positive_dimensions["compliance_trust"] > 0
    assert positive_dimensions["operational_reliability"] > 0
    assert negative_dimensions["csr"] > 0
    assert negative_dimensions["facilities"] > 0


def test_software_platform_summary_prioritizes_business_native_signals_and_dedupes_aliases():
    profile = {
        "projects": [
            {
                "project_name": "Trust-layer anti-fraud platform",
                "description": "Patented anti-fraud trust layer embedded into the communications platform for enterprise customers.",
                "category": "Security / Anti-phishing",
            },
            {
                "project_name": "Trust-layer platform",
                "description": "Commercial rollout of the anti-fraud product across partner channels.",
                "category": "Security / Anti-phishing",
            },
            {
                "project_name": "Trust platform",
                "description": "Short-form alias used in the annual report for the same product family.",
                "category": "Security / Anti-phishing",
            },
            {
                "project_name": "Project 1",
                "description": "Intangible assets under development with no clear business impact described.",
                "category": "Accounting placeholder",
            },
        ],
        "promises": [],
        "initiatives": [
            {
                "initiative": "Scaled enterprise communication platform deployments through operator and ecosystem partnerships across multiple international markets.",
                "category": "Regional Deployment / Partnerships",
                "benefit": "Expands enterprise customer reach and channel distribution",
            },
            {
                "initiative": "Expanded active-active observability, API-first automation and throughput capacity for enterprise messaging workflows.",
                "category": "Platform Operations & Reliability",
                "benefit": "Improves reliability and deployment economics",
            },
            {
                "initiative": "Operated employee commuting buses and transport support for staff.",
                "category": "Transport / Low-emission Commuting",
                "benefit": "Facilities support",
            },
            {
                "initiative": "Supported school and community programs in local areas.",
                "category": "Community / Infrastructure",
                "benefit": "CSR support",
            },
            {
                "initiative": "Strengthened anti-fraud and anti-abuse controls as a compliance-by-design product differentiator.",
                "category": "Security & Compliance",
                "benefit": "Improves customer trust and fraud prevention",
            },
        ],
        "capital_allocation": [],
    }

    summary = generator.build_summary(
        profile,
        business_context={"business_dnas": ["Enterprise Platform", "Compliance Infrastructure"]},
    )

    assert summary["major_projects"] == ["Trust-layer anti-fraud platform"]
    assert set(summary["management_focus_areas"][:3]) == {
        "Regional Deployment / Partnerships",
        "Platform Operations & Reliability",
        "Security & Compliance",
    }
    assert "Transport / Low-emission Commuting" not in summary["management_focus_areas"]
    assert "Community / Infrastructure" not in summary["management_focus_areas"]
    assert set(summary["key_initiatives"][:3]) == {
        "Scaled enterprise communication platform deployments through operator and ecosystem partnerships across multiple international markets.",
        "Expanded active-active observability, API-first automation and throughput capacity for enterprise messaging workflows.",
        "Strengthened anti-fraud and anti-abuse controls as a compliance-by-design product differentiator.",
    }


def test_software_platform_summary_filters_lower_signal_noise_more_aggressively():
    profile = {
        "projects": [],
        "promises": [
            {
                "promise": "Maintain employee counselling and extracurricular support programs.",
                "category": "People / Wellness",
            },
            {
                "promise": "Maintain active-active reliability, operator integrations, and compliance-by-design controls across the platform.",
                "category": "Platform Reliability / Compliance",
            },
        ],
        "initiatives": [
            {
                "initiative": "Expanded international partner-led customer deployments across enterprise channels.",
                "category": "Regional Deployment / Partnerships",
                "benefit": "Increases enterprise platform reach",
            },
            {
                "initiative": "Supported academic and community programs near operating sites.",
                "category": "Community / Infrastructure",
                "benefit": "CSR support",
            },
            {
                "initiative": "Revised compensation and retention programs for staff.",
                "category": "Compensation & Retention",
                "benefit": "HR support",
            },
        ],
        "capital_allocation": [],
    }

    summary = generator.build_summary(
        profile,
        business_context={"business_dnas": ["Enterprise Platform", "Compliance Infrastructure"]},
    )

    assert summary["management_focus_areas"] == ["Regional Deployment / Partnerships"]
    assert summary["key_initiatives"] == [
        "Expanded international partner-led customer deployments across enterprise channels."
    ]
    assert summary["major_promises"] == [
        "Maintain active-active reliability, operator integrations, and compliance-by-design controls across the platform."
    ]


def test_software_platform_promise_ranking_downweights_hr_noise_even_with_platform_context():
    profile = {
        "projects": [],
        "promises": [
            {
                "promise": "Provide structured induction modules and onboarding support for new hires.",
                "category": "People / Onboarding",
                "source_chunk": (
                    "The company discussed products, platforms, APIs, customer deployments, "
                    "and compliance capabilities in the same workforce section."
                ),
            },
            {
                "promise": "Maintain secure SDLC controls, vulnerability scanning, and incident response readiness across production systems.",
                "category": "Security / Platform Assurance",
                "source_chunk": (
                    "Security is embedded into development and operations through DevSecOps, "
                    "continuous monitoring, and cloud security posture management."
                ),
            },
        ],
        "initiatives": [],
        "capital_allocation": [],
    }

    summary = generator.build_summary(
        profile,
        business_context={"business_dnas": ["Enterprise Platform", "Compliance Infrastructure"]},
    )

    assert summary["major_promises"] == [
        "Maintain secure SDLC controls, vulnerability scanning, and incident response readiness across production systems."
    ]


def test_software_platform_promise_ranking_promotes_security_and_reliability_commitments():
    profile = {
        "projects": [],
        "promises": [
            {
                "promise": "Operate continuous threat detection, SIEM monitoring, and incident response escalation across live platform environments.",
                "category": "Security Operations",
            },
            {
                "promise": "Ensure robust and secure cloud infrastructure configurations through cloud security posture management.",
                "category": "Infrastructure Security",
            },
            {
                "promise": "Implement a decarbonisation roadmap and renewable energy transition plan across offices and data centres.",
                "category": "Sustainability / ESG",
            },
            {
                "promise": "Maintain defined consultation and notice periods during organizational changes.",
                "category": "People / HR Policy",
            },
        ],
        "initiatives": [],
        "capital_allocation": [],
    }

    summary = generator.build_summary(
        profile,
        business_context={"business_dnas": ["Enterprise Platform", "Compliance Infrastructure"]},
    )

    assert summary["major_promises"] == [
        "Operate continuous threat detection, SIEM monitoring, and incident response escalation across live platform environments.",
        "Ensure robust and secure cloud infrastructure configurations through cloud security posture management.",
    ]
