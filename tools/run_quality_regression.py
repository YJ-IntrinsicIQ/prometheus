import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from knowledge.quality_regression import parse_company_selector, run_quality_regression  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--companies",
        required=True,
        help="Use 'all' or a comma-separated company list.",
    )
    parser.add_argument("--companies-root", required=True, help="absolute companies root (there is no default)")
    parser.add_argument("--authorize-served-write", action="store_true", help="required when the root is the served companies/ tree")
    parser.add_argument(
        "--include-panel",
        action="store_true",
        help="Include panel-readiness scoring even when investor-panel artifacts are absent.",
    )
    parser.add_argument(
        "--output-md",
        action="store_true",
        help="Retained for compatibility; markdown output is written by default.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    companies = parse_company_selector(args.companies, companies_root=args.companies_root)
    outputs = run_quality_regression(
        companies=companies,
        companies_root=args.companies_root,
        include_panel=args.include_panel,
        authorize_served_write=args.authorize_served_write,
    )
    for name, path in outputs.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
