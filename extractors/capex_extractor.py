import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.base_extractor import BaseExtractor  # noqa: E402
from models.capex import CapexProject  # noqa: E402


PROMPT = """
You are an expert financial document extraction engine.

Return ONLY valid JSON (no markdown fences) with exactly these keys:

- project_name (string or null)
- allocated_budget (number in crore INR, e.g. 500 for ₹500 Cr, or null)
- budget_evidence (exact quote supporting budget, or null)
- location (string or null)
- location_evidence (exact quote supporting location, or null)
- capacity_increase_percent (number, e.g. 40 for 40%, or null)
- capacity_evidence (exact quote supporting capacity, or null)
- target_completion_date (string or null)
- completion_evidence (exact quote supporting completion date, or null)
- ownership_type (string or null)
- source_chunk (string or null)

Rules:
- Use only these key names. Do not invent different field names.
- If a field is not explicitly stated, return null.
- Do NOT infer or guess.
- Evidence fields must be exact quotes from the text.
"""


def create_extractor():
    return BaseExtractor(
        input_file="capex_discovery_results.json",
        output_file="extracted_capex.json",
        prompt=PROMPT,
        output_key="capex_projects",
    )


def extract_capex(chunk: str) -> CapexProject:
    data = create_extractor().extract(chunk)
    data["source_chunk"] = chunk
    return CapexProject(**data)
