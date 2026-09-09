from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

@dataclass
class CompanyContext:

    company: str
    year: str
    # Quarter label within the fiscal year ("Q1"–"Q4").
    # None for annual processing — all annual properties behave identically.
    # Set from the manifest's fiscal_quarter; never inferred from path or filename.
    quarter: Optional[str] = None

    @property
    def company_root(self):

        return (
            Path("companies")
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

    company: str
    eligible_years: tuple[str, ...] = ()
    year_eligibility_manifest: dict = field(default_factory=dict)
    year: Optional[str] = None

    @property
    def company_root(self):

        return (
            Path("companies")
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
