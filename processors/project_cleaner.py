import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.base_cleaner import BaseCleaner  # noqa: E402
from knowledge.temporal_event_splitter import PROJECT_SPLITTER  # noqa: E402


INPUT_FILE = "extracted_projects.json"
OUTPUT_FILE = "clean_projects.json"


REJECT_NAMES = {
    "capital work in progress",
    "capital-work-in progress (cwip)",
    "cwip",
    "projects in progress",
    "projects temporarily suspended",
}


def normalize_name(name):
    name = (
        name.lower()
        .replace("-", " ")
        .strip()
    )

    words_to_remove = [
        "project",
        "initiative",
        "company",
        "the",
    ]

    for word in words_to_remove:
        name = name.replace(
            word,
            "",
        )

    return " ".join(
        name.split()
    )


def classify_project(project):
    text = (
        project.get("project_name", "")
        + " "
        + project.get("description", "")
    ).lower()

    capital_terms = [
        "facility",
        "plant",
        "factory",
        "manufacturing",
        "expansion",
        "solar",
        "construction",
    ]

    for term in capital_terms:
        if term in text:
            return "capital_project"

    return "operational_initiative"


class ProjectCleaner(BaseCleaner):
    def is_valid(self, project):
        name = normalize_name(
            project.get(
                "project_name",
                "",
            )
        )

        description = (
            project.get(
                "description",
                "",
            )
            .strip()
        )

        if not name:
            return False

        if any(
            reject in name
            for reject in REJECT_NAMES
        ):
            return False

        if not description:
            return False

        return True

    def clean_item(self, project):
        """Apply temporal event splitting then classify project."""
        # First, split compound project items
        split_items = PROJECT_SPLITTER.split(project)

        # If split, return the list of split items
        if len(split_items) > 1:
            # Apply classification to each split item
            for item in split_items:
                item = dict(item)
                item["category"] = classify_project(item)
                if not str(item.get("status") or "").strip():
                    item["status"] = "UNKNOWN"
                    if not str(item.get("uncertainty_reason") or "").strip():
                        item["uncertainty_reason"] = "Project status was not explicit in the source disclosure."
            return split_items

        # Single item - apply existing logic
        project = dict(project)
        project["category"] = classify_project(project)

        if not str(project.get("status") or "").strip():
            project["status"] = "UNKNOWN"
            if not str(project.get("uncertainty_reason") or "").strip():
                project["uncertainty_reason"] = "Project status was not explicit in the source disclosure."

        return project

    def confidence_score(self, project):
        score = 0

        if project.get("location"):
            score += 1

        if project.get("status"):
            score += 1

        if project.get("description"):
            score += 1

        if score == 3:
            return "high"

        if score == 2:
            return "medium"

        return "low"

    def deduplicate(self, projects):
        seen = {}

        for project in projects:
            key = normalize_name(
                project["project_name"]
            )

            if key not in seen:
                seen[key] = project

        return list(seen.values())

    def report(self, projects, cleaned, removed):
        print(
            f"Original: {len(projects)}"
        )

        print(
            f"Cleaned: {len(cleaned)}"
        )

        print(
            f"Saved: {self.output_file}"
        )

        print("\nRemoved Projects:")

        for project in projects:
            if not self.is_valid(project):
                print(
                    "-",
                    project["project_name"],
                )


def is_valid_project(project):
    return create_cleaner().is_valid(project)


def confidence_score(project):
    return create_cleaner().confidence_score(project)


def deduplicate(projects):
    return create_cleaner().deduplicate(projects)


def create_cleaner():
    return ProjectCleaner(
        INPUT_FILE,
        OUTPUT_FILE,
        module_name="projects",
    )


def main():
    create_cleaner().run()


if __name__ == "__main__":
    main()
