import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.company_context import CompanyContext  # noqa: E402
from pipelines.pipeline_context import set_context  # noqa: E402
from knowledge.business_understanding import run_business_understanding  # noqa: E402


def get_discovery_steps():
    from discovery.project_discovery import main as project_discovery_main  # noqa: E402
    from discovery.promise_discovery import main as promise_discovery_main  # noqa: E402
    from discovery.risk_discovery import main as risk_discovery_main  # noqa: E402
    from discovery.capacity_discovery import main as capacity_discovery_main  # noqa: E402
    from discovery.capital_allocation_discovery import main as capital_allocation_discovery_main  # noqa: E402
    from discovery.initiative_discovery import main as initiative_discovery_main  # noqa: E402

    return [
        ("Project Discovery", project_discovery_main),
        ("Promise Discovery", promise_discovery_main),
        ("Risk Discovery", risk_discovery_main),
        ("Capacity Discovery", capacity_discovery_main),
        ("Capital Allocation Discovery", capital_allocation_discovery_main),
        ("Initiative Discovery", initiative_discovery_main),
    ]


def get_extraction_steps():
    from extractors.project_extractor import main as project_extractor_main  # noqa: E402
    from extractors.promise_extractor import main as promise_extractor_main  # noqa: E402
    from extractors.risk_extractor import main as risk_extractor_main  # noqa: E402
    from extractors.capacity_extractor import main as capacity_extractor_main  # noqa: E402
    from extractors.capital_allocation_extractor import main as capital_allocation_extractor_main  # noqa: E402
    from extractors.initiative_extractor import main as initiative_extractor_main  # noqa: E402

    return [
        ("Project Extractor", project_extractor_main),
        ("Promise Extractor", promise_extractor_main),
        ("Risk Extractor", risk_extractor_main),
        ("Capacity Extractor", capacity_extractor_main),
        ("Capital Allocation Extractor", capital_allocation_extractor_main),
        ("Initiative Extractor", initiative_extractor_main),
    ]


def get_cleaning_steps():
    from processors.project_cleaner import main as project_cleaner_main  # noqa: E402
    from processors.promise_cleaner import main as promise_cleaner_main  # noqa: E402
    from processors.risk_cleaner import main as risk_cleaner_main  # noqa: E402
    from processors.capacity_cleaner import main as capacity_cleaner_main  # noqa: E402
    from processors.capital_allocation_cleaner import main as capital_allocation_cleaner_main  # noqa: E402
    from processors.initiative_cleaner import main as initiative_cleaner_main  # noqa: E402

    return [
        ("Project Cleaner", project_cleaner_main),
        ("Promise Cleaner", promise_cleaner_main),
        ("Risk Cleaner", risk_cleaner_main),
        ("Capacity Cleaner", capacity_cleaner_main),
        ("Capital Allocation Cleaner", capital_allocation_cleaner_main),
        ("Initiative Cleaner", initiative_cleaner_main),
    ]


def get_intelligence_steps():
    from knowledge.cim_builder import main as cim_builder_main  # noqa: E402
    from synthesis.management_profile_builder import main as management_profile_builder_main  # noqa: E402
    from synthesis.management_summary_generator import main as management_summary_generator_main  # noqa: E402
    from synthesis.theme_builder import main as theme_builder_main  # noqa: E402
    from synthesis.entity_linker import main as entity_linker_main  # noqa: E402
    from synthesis.management_focus_analyzer import main as management_focus_analyzer_main  # noqa: E402
    from synthesis.promise_execution_tracker import main as promise_execution_tracker_main  # noqa: E402
    from synthesis.evidence_graph_builder import main as evidence_graph_builder_main  # noqa: E402
    from synthesis.investor_narrative_generator import main as investor_narrative_generator_main  # noqa: E402

    return [
        ("Company Intelligence Builder", cim_builder_main),
        ("Management Profile Builder", management_profile_builder_main),
        ("Management Summary Generator", management_summary_generator_main),
        ("Theme Builder", theme_builder_main),
        ("Entity Linker", entity_linker_main),
        ("Management Focus Analyzer", management_focus_analyzer_main),
        ("Promise Execution Tracker", promise_execution_tracker_main),
        ("Evidence Graph Builder", evidence_graph_builder_main),
        ("Investor Narrative Generator", investor_narrative_generator_main),
    ]


STAGES = {
    "discovery": ("DISCOVERY", get_discovery_steps),
    "extraction": ("EXTRACTION", get_extraction_steps),
    "cleaning": ("CLEANING", get_cleaning_steps),
    "intelligence": ("INTELLIGENCE", get_intelligence_steps),
}


def run_steps(stage_label, steps):
    if callable(steps):
        steps = steps()

    for step_label, step in steps:
        print(
            f"[{stage_label}] {step_label}"
        )
        step()


def run_business_understanding_stage():
    run_business_understanding()


def run_discovery():
    run_steps(
        *STAGES["discovery"]
    )


def run_extraction():
    run_steps(
        *STAGES["extraction"]
    )


def run_cleaning():
    run_steps(
        *STAGES["cleaning"]
    )


def run_intelligence():
    run_steps(
        *STAGES["intelligence"]
    )


def run_all():
    run_business_understanding_stage()
    run_discovery()
    run_extraction()
    run_cleaning()
    run_intelligence()


def build_parser():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "company"
    )

    parser.add_argument(
        "year"
    )

    parser.add_argument(
        "--stage",
        choices=[
            "all",
            "business_understanding",
            "discovery",
            "extraction",
            "cleaning",
            "intelligence",
        ],
        default="all",
    )

    return parser


def main():
    args = build_parser().parse_args()

    context = CompanyContext(
        company=args.company,
        year=args.year,
    )

    context.create_directories()
    set_context(context)

    if args.stage == "all":
        run_all()
    elif args.stage == "business_understanding":
        run_business_understanding_stage()
    elif args.stage == "discovery":
        run_discovery()
    elif args.stage == "extraction":
        run_extraction()
    elif args.stage == "cleaning":
        run_cleaning()
    elif args.stage == "intelligence":
        run_intelligence()

    print(
        f"Raw: {context.raw_dir}"
    )

    print(
        f"Extracted: {context.extracted_dir}"
    )

    print(
        f"Intelligence: {context.intelligence_dir}"
    )


if __name__ == "__main__":
    main()
