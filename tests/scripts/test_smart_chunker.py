import json

from scripts import smart_chunker


def test_chunk_pages_persists_clean_chunks_json(tmp_path):
    pages = [
        {
            "page": 1,
            "text": "This is the first paragraph of the annual report and it contains enough content to survive the paragraph cleaning threshold because it is intentionally long enough to exceed the minimum length requirement for chunking.\n\nThis is the second paragraph of the annual report and it also contains enough content to survive the paragraph cleaning threshold because it is intentionally long enough to exceed the minimum length requirement for chunking.",
        }
    ]
    output_path = tmp_path / "clean_chunks.json"

    chunks = smart_chunker.chunk_pages(
        pages,
        company="polymatech",
        year="2024",
        document_type="annual_report",
        output_path=output_path,
    )

    assert len(chunks) == 1

    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["company"] == "polymatech"
    assert payload["year"] == "2024"
    assert payload["document_type"] == "annual_report"
    assert payload["chunk_count"] == 1
    assert len(payload["chunks"]) == 1
    assert payload["chunks"][0]["chunk_id"] == "CHK-000001"
    assert payload["chunks"][0]["metadata"]["page"] == 1
    assert payload["chunks"][0]["text"]


def test_chunk_pages_preserves_compact_financial_statement_rows(tmp_path):
    pages = [
        {
            "page": 241,
            "text": (
                "Consolidated Balance Sheet\n\n"
                "ASSETS\n\n"
                "Total current assets 638,602.9 525,940.6\n\n"
                "TOTAL ASSETS 1,087,852.2 921,005.8\n\n"
                "Consolidated Statement of Cash Flow\n\n"
                "Cash generated from operations 147,331.2 145,489.3\n\n"
                "Net cash generated from / (used in) operating activities (A) 124,191.8 140,720.9"
            ),
        }
    ]

    chunks = smart_chunker.chunk_pages(
        pages,
        company="acme",
        year="fy26",
        document_type="annual_report",
        output_path=tmp_path / "clean_chunks.json",
    )

    combined = "\n".join(chunk["text"] for chunk in chunks)
    assert "TOTAL ASSETS 1,087,852.2 921,005.8" in combined
    assert "Net cash generated from / (used in) operating activities (A) 124,191.8 140,720.9" in combined
