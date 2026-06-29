CAPEX_KEYWORDS = [
    "capacity",
    "expansion",
    "plant",
    "facility",
    "manufacturing",
    "capex",
    "capital expenditure",
    "investment",
    "production",
    "commissioning",
    "greenfield",
    "brownfield"
]

CAPEX_POSITIVE = [
    "capacity expansion",
    "capital expenditure",
    "capex",
    "greenfield",
    "brownfield",
    "new plant",
    "new facility",
    "cwip",
    "capacity increase",
    "commercial production"
]

CAPEX_NEGATIVE = [
    "agm",
    "notice",
    "voting",
    "auditor",
    "director",
    "scrutinizer"
]


def is_capex_related(text):

    text = text.lower()

    for keyword in CAPEX_KEYWORDS:

        if keyword in text:
            return True

    return False