import json
import re
from pathlib import Path


TARGET_CHUNK_SIZE = 1200
OVERLAP_PARAGRAPHS = 1


def is_mostly_numeric(text: str) -> bool:

    tokens = text.split()

    if not tokens:
        return False

    numeric_tokens = 0

    for token in tokens:

        cleaned = token.replace(",", "").replace(".", "")

        if cleaned.isdigit():
            numeric_tokens += 1

    return (
        numeric_tokens / len(tokens)
    ) > 0.6


def looks_like_table_row(text: str) -> bool:
    """Keep compact table rows that would otherwise be lost as short text."""
    if not text or not re.search(r"[A-Za-z]", text):
        return False
    numeric_tokens = re.findall(r"\(?\d[\d,]*(?:\.\d+)?\)?%?", text)
    if len(numeric_tokens) < 2:
        return False
    if re.search(r"\b(?:basic|diluted)\s*\(in\s+[^)]+\)", text, re.I):
        return True
    # G3: a short line "(iv) Other bank balances 13 8 1,827" (label, note reference, two amounts) was dropped because 'bank' is not in the keyword list below.
    # Two or more amounts, at least one formatted as an amount (comma/decimal/brackets), and a label of two or more words is a statement row.
    label_words = re.findall(r"[A-Za-z]{3,}", text)
    if len(label_words) >= 2 and len(text) < 150 and any(("," in tok or tok.startswith("(") or re.fullmatch(r"\d+\.\d{2}", tok)) for tok in numeric_tokens):
        return True
    return bool(
        re.search(
            r"\b(total|assets?|liabilities|equity|revenue|income|profit|tax|cash|"
            r"operating|investing|financing|borrowings?|receivables?|inventories|"
            r"investments?|goodwill|intangible|depreciation|amortisation|amortization|"
            r"dividend|reserves?|capital|expenses?)\b",
            text,
            re.IGNORECASE,
        )
    )


_CELL_NUMBER = re.compile(r"[\(\[]?-?\d[\d,]*(?:\.\d+)?[\)\]]?%?|[-\u2013\u2014]")
_SECTION_MARKER = re.compile(r"[IVX]{1,4}\.")
_PL_TITLE = re.compile(r"profit\s+and\s+loss\s+account|statement\s+of\s+profit\s+and\s+loss|income\s+statement|balance\s+sheet\s+as\s+at", re.I)


def split_cell_lines(raw: str):
    """A statement page whose PDF text puts every table cell on its own line, with no blank line between rows, used to be collapsed into one blob in which no row could be
    recognised (a bank's profit-and-loss account on one page became a single paragraph). Rebuild the rows instead: label lines accumulate until the numeric cells that
    follow them, and each label plus its cells becomes one paragraph. Returns None unless the block really has the cell-per-line shape of an income statement."""
    lines = [line.strip() for line in raw.split("\n") if line.strip()]
    # Scope: an income statement page. Other statements (cash flow, balance sheet) are already recognised from their existing paragraph shape and are left alone.
    head = " ".join(lines[:15])
    body = " ".join(lines)
    is_income_statement = bool(_PL_TITLE.search(head)) or bool(re.search(r"\bINCOME\b", body) and re.search(r"\bEXPENDITURE\b", body))
    if not is_income_statement:
        return None
    numeric = [bool(_CELL_NUMBER.fullmatch(line)) for line in lines]
    if len(lines) < 12 or sum(numeric) < 6 or sum(numeric) < 0.25 * len(lines):
        return None
    rows, labels, cells = [], [], []
    for line, is_number in zip(lines, numeric):
        if is_number:
            cells.append(line)
            continue
        if cells:
            rows.append(" ".join(labels + cells))
            labels, cells = [], []
        elif labels and _SECTION_MARKER.fullmatch(line):     # "I." / "II." opens a new section: what came before (title, signatures) is its own paragraph
            rows.append(" ".join(labels))
            labels = []
        labels.append(line)
    if labels or cells:
        rows.append(" ".join(labels + cells))
    return rows


# A balance-sheet section heading on a line of its own ("Liabilities (1) Non-current liabilities (a) Financial liabilities"). It carries no figure, but the rows beneath it ("(i) Borrowings 21
# 8,981.3") are only distinguishable from the current section's rows by it: dropped as a short non-row, the non-current borrowings read as a second bare "(i) Borrowings".
_SECTION_HEADING = re.compile(r"^\W*(?:liabilities\W+)?(?:\(?\d\)?\W+)?(?:non[-\s]?current|current)\s+(?:liabilities|assets)(?:\W+\(?[a-z]\)?\W+financial\s+(?:liabilities|assets))?\W*$", re.I)


def clean_paragraphs(text: str):

    raw_paragraphs = []
    for block in re.split(r"\n\s*\n", text):
        rows = split_cell_lines(block)
        raw_paragraphs.extend(rows if rows is not None else [block])

    paragraphs = []

    for para in raw_paragraphs:

        para = re.sub(
            r"\s+",
            " ",
            para
        ).strip()

        is_table_row = looks_like_table_row(para)

        if len(para) < 150 and not is_table_row and not _SECTION_HEADING.match(para):
            continue

        if is_mostly_numeric(para) and not is_table_row:
            continue

        paragraphs.append(
            para
        )

    return paragraphs


def chunk_text(
    text: str,
    target_chunk_size: int = TARGET_CHUNK_SIZE
):

    paragraphs = clean_paragraphs(
        text
    )

    chunks = []

    current_chunk = []
    current_size = 0

    for para in paragraphs:

        para_size = len(para)

        if (
            current_size + para_size
            <= target_chunk_size
        ):

            current_chunk.append(
                para
            )

            current_size += para_size

        else:

            chunk_text_value = "\n\n".join(
                current_chunk
            )

            if chunk_text_value.strip():
                chunks.append(
                    chunk_text_value
                )

            overlap = (
                current_chunk[
                    -OVERLAP_PARAGRAPHS:
                ]
                if current_chunk
                else []
            )

            current_chunk = (
                overlap + [para]
            )

            current_size = sum(
                len(x)
                for x in current_chunk
            )

    if current_chunk:

        final_chunk = "\n\n".join(
            current_chunk
        )
        if final_chunk.strip():
            chunks.append(
                final_chunk
            )

    return chunks

def _build_chunk_id(index: int) -> str:
    return f"CHK-{index + 1:06d}"


def persist_clean_chunks(
    chunks,
    *,
    company: str = "",
    year: str = "",
    document_type: str = "annual_report",
    output_path=None,
):
    output_path = Path(output_path) if output_path is not None else None

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "company": company or "",
        "year": year or "",
        "document_type": document_type or "annual_report",
        "chunk_count": len(chunks),
        "chunks": [
            {
                "chunk_id": chunk.get("chunk_id") or _build_chunk_id(index),
                "page": chunk.get("page"),
                "text": chunk.get("text", ""),
                "metadata": {
                    "page": chunk.get("page"),
                    "company": company or "",
                    "year": year or "",
                    "document_type": document_type or "annual_report",
                },
            }
            for index, chunk in enumerate(chunks)
        ],
    }

    seen_chunk_ids = set()
    for index, chunk in enumerate(payload["chunks"]):
        chunk_id = chunk.get("chunk_id") or _build_chunk_id(index)
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            raise ValueError("chunk_id is required")
        if chunk_id in seen_chunk_ids:
            raise ValueError(f"duplicate chunk_id: {chunk_id}")
        seen_chunk_ids.add(chunk_id)

        if not isinstance(chunk.get("text"), str) or not chunk.get("text", "").strip():
            raise ValueError(f"chunk {chunk_id} must contain text")
        if chunk.get("page") is None:
            raise ValueError(f"chunk {chunk_id} must contain page")
        metadata = chunk.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError(f"chunk {chunk_id} must include metadata")
        for field in ("page", "company", "year", "document_type"):
            if field not in metadata:
                raise ValueError(f"chunk {chunk_id} missing metadata field {field}")

    if output_path is not None:
        output_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    return payload


def chunk_pages(
    pages,
    *,
    company: str = "",
    year: str = "",
    document_type: str = "annual_report",
    output_path=None,
):

    all_chunks = []

    for page_data in pages:

        page_number = page_data["page"]

        page_chunks = chunk_text(
            page_data["text"]
        )

        for chunk in page_chunks:
            all_chunks.append(
                {
                    "page": page_number,
                    "text": chunk,
                }
            )

    if output_path is not None or any([company, year, document_type]):
        persist_clean_chunks(
            all_chunks,
            company=company,
            year=year,
            document_type=document_type,
            output_path=output_path,
        )

    return all_chunks
