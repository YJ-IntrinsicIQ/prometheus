#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from knowledge.ai import get_llm  # noqa: E402


def main() -> int:
    llm = get_llm()
    response = llm.generate(prompt="Reply with exactly: Hello Prometheus")

    print(f"Provider: {response.provider}")
    print(f"Model: {response.model}")
    print(f"Latency: {response.latency_ms:.2f}ms")
    print(
        "Tokens: "
        f"prompt={response.prompt_tokens}, "
        f"completion={response.completion_tokens}, "
        f"total={response.total_tokens}"
    )
    print(f"Response: {response.text}")

    if response.text.strip() == "Hello Prometheus":
        print("PASS")
        return 0

    print("FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
