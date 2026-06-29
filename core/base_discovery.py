import json
from pathlib import Path

from discovery.discovery_engine import (
    keyword_discovery,
    merge_results,
    semantic_discovery,
)
from core.context_paths import discovery_path
from pipelines.pipeline_context import get_context


ROOT = Path(__file__).resolve().parent.parent
CHROMA_PATH = ROOT / "chroma_db"


class BaseDiscovery:
    def __init__(
        self,
        queries,
        positive_patterns,
        negative_patterns,
        output_file,
        document_type=None,
    ):
        self.queries = queries
        self.positive_patterns = positive_patterns
        self.negative_patterns = negative_patterns
        self.output_file = discovery_path(output_file)
        self.document_type = document_type

        context = get_context()
        self.company = getattr(context, "company", None)
        self.year = getattr(context, "year", None)

    def run(self):
        semantic = semantic_discovery(
            self.queries,
            company=self.company,
            year=self.year,
            document_type=self.document_type,
        )

        keyword = keyword_discovery(
            CHROMA_PATH,
            self.positive_patterns,
            self.negative_patterns,
            company=self.company,
            year=self.year,
            document_type=self.document_type,
        )

        results = merge_results(
            semantic,
            keyword,
        )

        with open(
            self.output_file,
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(
                results,
                f,
                indent=2,
                ensure_ascii=False,
            )

        return results
