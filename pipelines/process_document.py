"""Minimal CLI for the canonical document processing entry point.

Usage:
    python pipelines/process_document.py <file> [--execute]

This calls process_document() from knowledge/document_processor.py and prints
a structured JSON result.  It does NOT duplicate any routing logic — the
canonical path is always process_document().

Options:
    --execute    Invoke the processor after routing (annual reports only).
                 Default: identify and route only.
    --json       Print the full result dict as JSON.

Exit codes:
    0  ROUTED or EXECUTED
    1  REVIEW_REQUIRED, UNSUPPORTED, REJECTED, or ERROR
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from knowledge.document_processor import ProcessorStatus, process_document  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="process_document",
        description="Identify, route, and optionally process a raw document.",
    )
    parser.add_argument("file", help="Path to the raw document file.")
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Invoke the processor after routing (requires explicit intent).",
    )
    parser.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        default=False,
        help="Print the full result as JSON.",
    )
    args = parser.parse_args(argv)

    path = Path(args.file)
    result = process_document(path, execute=args.execute)

    if args.output_json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print_human(result)

    success = result.status in (ProcessorStatus.ROUTED, ProcessorStatus.EXECUTED)
    return 0 if success else 1


def _print_human(result) -> None:
    from knowledge.document_processor import ProcessorStatus

    status_emoji = {
        ProcessorStatus.ROUTED: "✓",
        ProcessorStatus.EXECUTED: "✓",
        ProcessorStatus.REVIEW_REQUIRED: "⚠",
        ProcessorStatus.UNSUPPORTED: "○",
        ProcessorStatus.REJECTED: "✗",
        ProcessorStatus.ERROR: "✗",
        ProcessorStatus.IDENTIFIED_ONLY: "→",
    }
    icon = status_emoji.get(result.status, "?")
    print(f"{icon}  Status:  {result.status.value}")

    if result.manifest:
        m = result.manifest
        print(f"   Company: {m.company_identity.resolved_company_key or '(unresolved)'}")
        fy = m.reporting_period.fiscal_year if m.reporting_period else "(unresolved)"
        print(f"   Period:  {fy}")
        print(f"   Source:  {m.document_identity.source_type.value}")
        print(f"   ClassStatus: {m.classification.status.value}")

    if result.routing:
        r = result.routing
        print(f"   Route:   {r.route}")
        print(f"   Processor: {r.processor.value}")
        if r.destination:
            print(f"   Destination: {r.destination}")

    if result.processor_output:
        po = result.processor_output
        print(f"   LegacyInputs: company={po.company} year={po.year}")

    if result.error:
        print(f"   Error:   {result.error}")

    for w in result.warnings:
        print(f"   Warning: {w}")

    print(f"   Elapsed: {result.elapsed_seconds}s")


if __name__ == "__main__":
    sys.exit(main())
