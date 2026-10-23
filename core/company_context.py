from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

def _resolve_root(companies_root, authorize_served_write):
    # imported here: core.context_paths imports pipelines.pipeline_context, which imports this module
    from core.context_paths import resolve_output_root

    return resolve_output_root(companies_root, authorize_served=authorize_served_write)


def _logical(path, companies_root) -> str:
    from core.context_paths import logical_company_path

    return logical_company_path(path, companies_root)


@dataclass
class CompanyContext:
    """Where one company-year lives. The company-data root is EXPLICIT: an absolute path with no default and no cwd fallback. The served companies/ tree is
    refused unless authorize_served_write=True. Every directory below is absolute; use logical() when a path is recorded inside an artifact."""

    company: str
    year: str
    companies_root: Path
    # Quarter label within the fiscal year ("Q1"–"Q4").
    # None for annual processing — all annual properties behave identically.
    # Set from the manifest's fiscal_quarter; never inferred from path or filename.
    quarter: Optional[str] = None
    authorize_served_write: bool = False

    def __post_init__(self):
        self.companies_root = _resolve_root(self.companies_root, self.authorize_served_write)

    def logical(self, path) -> str:
        """The artifact-facing form of a path: companies/<slug>/..., independent of the absolute root this run used."""
        return _logical(path, self.companies_root)

    def planned_directories(self):
        """The directories create_directories() would create. Read-only."""
        return [self.raw_dir, self.extracted_dir, self.intelligence_dir, self.financials_dir]

    @property
    def company_root(self):

        return (
            self.companies_root
            / self.company
        )

    @property
    def year_root(self):

        return (
            self.company_root
            / self.year
        )

    @property
    def quarter_root(self):
        """Storage root for quarterly artifacts: companies/<co>/<fy>/quarters/<q>/

        Only meaningful when quarter is not None.  Annual code never sets quarter
        so this property is never accessed from the annual path.
        """
        if not self.quarter:
            raise ValueError(
                "quarter_root is only available when CompanyContext.quarter is set. "
                "Annual processing uses year_root instead."
            )
        return self.year_root / "quarters" / self.quarter

    @property
    def raw_dir(self):

        return (
            self.year_root
            / "raw"
        )

    @property
    def extracted_dir(self):

        return (
            self.year_root
            / "extracted"
        )

    @property
    def intelligence_dir(self):

        return (
            self.year_root
            / "intelligence"
        )

    @property
    def financials_dir(self):

        return (
            self.year_root
            / "financials"
        )

    @property
    def discovery_dir(self):

        return self.raw_dir


    @property
    def extraction_dir(self):

        return self.extracted_dir


    @property
    def synthesis_dir(self):

        return self.intelligence_dir

    def create_directories(self):

        self.raw_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        self.extracted_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        self.intelligence_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        self.financials_dir.mkdir(
            parents=True,
            exist_ok=True
        )


@dataclass
class CompanyMemoryContext:
    """Company-memory location. Same explicit-root contract as CompanyContext."""

    company: str
    companies_root: Path
    eligible_years: tuple[str, ...] = ()
    year_eligibility_manifest: dict = field(default_factory=dict)
    year: Optional[str] = None
    authorize_served_write: bool = False

    def __post_init__(self):
        self.companies_root = _resolve_root(self.companies_root, self.authorize_served_write)

    def logical(self, path) -> str:
        return _logical(path, self.companies_root)

    @property
    def company_root(self):

        return (
            self.companies_root
            / self.company
        )

    @property
    def year_root(self):

        return (
            self.company_root
            / "company_memory"
        )

    @property
    def raw_dir(self):

        return (
            self.year_root
            / "raw"
        )

    @property
    def extracted_dir(self):

        return (
            self.year_root
            / "extracted"
        )

    @property
    def intelligence_dir(self):

        return (
            self.year_root
            / "intelligence"
        )

    @property
    def financials_dir(self):

        return (
            self.year_root
            / "financials"
        )

    @property
    def company_memory_dir(self):

        return self.year_root

    @property
    def multi_year_dir(self):

        return (
            self.year_root
            / "multi_year"
        )

    @property
    def discovery_dir(self):

        return self.raw_dir

    @property
    def extraction_dir(self):

        return self.extracted_dir

    @property
    def synthesis_dir(self):

        return self.intelligence_dir

    def create_directories(self):

        self.year_root.mkdir(
            parents=True,
            exist_ok=True
        )

        self.raw_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        self.extracted_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        self.intelligence_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        self.financials_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        self.multi_year_dir.mkdir(
            parents=True,
            exist_ok=True
        )
