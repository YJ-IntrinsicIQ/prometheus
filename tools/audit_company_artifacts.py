import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from knowledge.artifact_audit import run_company_artifact_audit  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("company")
    parser.add_argument("--companies-root", required=True, help="absolute companies root (there is no default)")
    parser.add_argument("--authorize-served-write", action="store_true", help="required when the root is the served companies/ tree")
    parser.add_argument(
        "--fix-safe",
        action="store_true",
        help="Apply only deterministic safe repairs before writing the audit output.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    outputs = run_company_artifact_audit(args.company, companies_root=args.companies_root, fix_safe=args.fix_safe, authorize_served_write=args.authorize_served_write)
    for name, path in outputs.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
