import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from configs.risks import (  # noqa: E402
    NEGATIVE_PATTERNS,
    POSITIVE_PATTERNS,
    QUERIES,
)
from core.base_discovery import BaseDiscovery  # noqa: E402


RISK_QUERIES = QUERIES


def create_discovery():
    return BaseDiscovery(
        queries=QUERIES,
        positive_patterns=POSITIVE_PATTERNS,
        negative_patterns=NEGATIVE_PATTERNS,
        output_file="risk_discovery_results.json",
    )


def main():
    results = create_discovery().run()

    print(
        f"Risk chunks found: {len(results)}"
    )


if __name__ == "__main__":
    main()
