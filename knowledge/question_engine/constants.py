VALID_PRIORITIES = {1, 2, 3, 4, 5}

PRIORITY_CRITICAL = 1
PRIORITY_HIGH = 2
PRIORITY_MEDIUM = 3
PRIORITY_LOW = 4
PRIORITY_OPTIONAL = 5

OUTPUT_STRUCTURED = "structured"
OUTPUT_SUMMARY = "summary"
OUTPUT_BOOLEAN = "boolean"

VALID_OUTPUT_TYPES = {
    OUTPUT_STRUCTURED,
    OUTPUT_SUMMARY,
    OUTPUT_BOOLEAN,
}

MODULE_CAPITAL_ALLOCATION = "capital_allocation"
MODULE_TECHNOLOGY = "technology"
MODULE_LIBRARY_ECONOMICS = "library_economics"
MODULE_PLATFORM_DEPENDENCY = "platform_dependency"
MODULE_PLATFORM_ECONOMICS = "platform_economics"
MODULE_COMPLIANCE_INFRASTRUCTURE = "compliance_infrastructure"

DEFAULT_DNA_MODULE_MAPPINGS = [
    {
        "business_dnas": [
            "Manufacturing",
            "Capital Intensive",
            "Asset Heavy",
        ],
        "module_ids": [
            MODULE_CAPITAL_ALLOCATION,
            MODULE_TECHNOLOGY,
        ],
    },
    {
        "business_dnas": [
            "Semiconductor",
            "Technology",
            "Technology Driven",
            "IP Driven",
            "Software",
            "IP Library",
            "Platform Monetization",
        ],
        "module_ids": [
            MODULE_TECHNOLOGY,
        ],
    },
    {
        "business_dnas": [
            "Enterprise Platform",
            "Compliance Infrastructure",
        ],
        "module_ids": [
            MODULE_TECHNOLOGY,
            MODULE_PLATFORM_DEPENDENCY,
            MODULE_PLATFORM_ECONOMICS,
        ],
    },
    {
        "business_dnas": [
            "Compliance Infrastructure",
        ],
        "module_ids": [
            MODULE_COMPLIANCE_INFRASTRUCTURE,
            MODULE_PLATFORM_DEPENDENCY,
            MODULE_TECHNOLOGY,
        ],
    },
    {
        "business_dnas": [
            "IP Library",
        ],
        "module_ids": [
            MODULE_LIBRARY_ECONOMICS,
        ],
    },
    {
        "business_dnas": [
            "Platform Monetization",
        ],
        "module_ids": [
            MODULE_PLATFORM_DEPENDENCY,
            MODULE_TECHNOLOGY,
        ],
    },
]

QUESTION_MODULE_ALIASES = {
    "capex": MODULE_CAPITAL_ALLOCATION,
    "capital allocation": MODULE_CAPITAL_ALLOCATION,
    "capital_allocation": MODULE_CAPITAL_ALLOCATION,
    "technology": MODULE_TECHNOLOGY,
    "innovation": MODULE_TECHNOLOGY,
    "library economics": MODULE_LIBRARY_ECONOMICS,
    "library_economics": MODULE_LIBRARY_ECONOMICS,
    "platform dependency": MODULE_PLATFORM_DEPENDENCY,
    "platform_dependency": MODULE_PLATFORM_DEPENDENCY,
    "platform economics": MODULE_PLATFORM_ECONOMICS,
    "platform_economics": MODULE_PLATFORM_ECONOMICS,
    "compliance infrastructure": MODULE_COMPLIANCE_INFRASTRUCTURE,
    "compliance_infrastructure": MODULE_COMPLIANCE_INFRASTRUCTURE,
}
