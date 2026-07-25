import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from knowledge.financials import run_fundamentals_acceptance  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", required=True)
    parser.add_argument("--year")
    parser.add_argument(
        "--output-md",
        action="store_true",
        help="Also write a markdown acceptance report alongside the JSON report.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    outputs = run_fundamentals_acceptance(
        company=args.company,
        year=args.year,
        output_md=args.output_md,
    )
    for name, path in outputs.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
