from dataclasses import dataclass
from pathlib import Path

@dataclass
class CompanyContext:

    company: str
    year: str

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