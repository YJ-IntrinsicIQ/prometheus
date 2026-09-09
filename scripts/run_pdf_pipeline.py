import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.pdf_reader import extract_text
from scripts.chunker import chunk_text

from extractors.capex_extractor import extract_capex
from consolidators.capex_consolidator import merge_projects

from filters.capex_filter import is_capex_related


_CANONICAL_PATH = ROOT / "data" / "Processed" / "polymatech" / "fy25" / "annual_report"
PDF_PATH = next(
    (p for p in sorted(_CANONICAL_PATH.glob("*.pdf")) if _CANONICAL_PATH.exists()),
    _CANONICAL_PATH / "polymatech_fy25.pdf",
)


def main():

    print("\nReading PDF...\n")

    text = extract_text(PDF_PATH)

    print(f"Total characters: {len(text)}")

    chunks = chunk_text(text)

    print(f"Total chunks: {len(chunks)}\n")

    extracted_projects = []

    for idx, chunk in enumerate(chunks):

        print(f"\nProcessing chunk {idx + 1}/{len(chunks)}")

        try:

            if not is_capex_related(chunk):
                continue

            print(
                f"Relevant Chunk Found: {idx + 1}"
            )

            project = extract_capex(chunk)

            # Ignore empty records
            if any([
                project.allocated_budget,
                project.location,
                project.capacity_increase_percent,
                project.target_completion_date
            ]):

                print("CAPEX FOUND:")
                print(project)

                extracted_projects.append(project)

        except Exception as e:

            print(
                f"Error in chunk {idx + 1}: {e}"
            )

    print("\n====================")
    print("CONSOLIDATING")
    print("====================\n")

    merged_projects = merge_projects(
        extracted_projects
    )

    print(
        f"Projects Found: {len(merged_projects)}"
    )

    for idx, project in enumerate(
        merged_projects,
        start=1
    ):

        print(f"\nPROJECT {idx}")
        print(project)


if __name__ == "__main__":
    main()
