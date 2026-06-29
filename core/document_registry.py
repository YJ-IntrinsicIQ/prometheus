import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from pipelines.pipeline_context import get_context


ROOT = Path(__file__).resolve().parent.parent


def normalize_company(company):
    if company is None:
        return None
    return str(company).strip().lower()


def normalize_year(year):
    if year is None:
        return None
    return str(year).strip().lower()


def normalize_document_type(document_type):
    if document_type is None:
        return None
    return str(document_type).strip().lower()


def metadata_filter(company=None, year=None, document_type=None):
    clauses = []

    company = normalize_company(company)
    original_year = None if year is None else str(year).strip()
    year = normalize_year(year)
    document_type = normalize_document_type(document_type)

    if company:
        clauses.append(
            {"company": company}
        )

    if year:
        year_values = list(
            dict.fromkeys(
                [
                    year,
                    original_year,
                    original_year.upper() if original_year else None,
                ]
            )
        )
        year_values = [
            value
            for value in year_values
            if value
        ]

        if len(year_values) == 1:
            clauses.append(
                {"year": year_values[0]}
            )
        else:
            clauses.append(
                {
                    "year": {
                        "$in": year_values
                    }
                }
            )

    if document_type:
        clauses.append(
            {"document_type": document_type}
        )

    if not clauses:
        return None

    if len(clauses) == 1:
        return clauses[0]

    return {
        "$and": clauses
    }


@dataclass
class DocumentRecord:
    company: str
    year: str
    document_type: str
    filename: str
    processed_timestamp: str


class DocumentRegistry:
    def __init__(
        self,
        company=None,
        year=None,
        registry_file=None,
    ):
        context = get_context()

        self.company = normalize_company(
            company or getattr(context, "company", None)
        )
        self.year = normalize_year(
            year or getattr(context, "year", None)
        )

        if registry_file:
            self.registry_file = Path(registry_file)
        elif context:
            self.registry_file = (
                context.raw_dir
                / "document_registry.json"
            )
        else:
            self.registry_file = (
                ROOT
                / "outputs"
                / "document_registry.json"
            )

    def load(self):
        if not self.registry_file.exists():
            return []

        with open(
            self.registry_file,
            "r",
            encoding="utf-8",
        ) as f:
            return json.load(f)

    def save(self, records):
        self.registry_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with open(
            self.registry_file,
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(
                records,
                f,
                indent=2,
                ensure_ascii=False,
            )

    def register(
        self,
        document_type,
        filename,
    ):
        document_type = normalize_document_type(
            document_type
        )

        record = DocumentRecord(
            company=self.company or "",
            year=self.year or "",
            document_type=document_type or "",
            filename=Path(filename).name,
            processed_timestamp=datetime.now(
                timezone.utc
            ).isoformat(),
        )

        records = self.load()
        record_data = asdict(record)

        records = [
            item
            for item in records
            if not (
                item.get("company") == record.company
                and item.get("year") == record.year
                and item.get("document_type") == record.document_type
                and item.get("filename") == record.filename
            )
        ]

        records.append(record_data)
        self.save(records)

        return record_data
