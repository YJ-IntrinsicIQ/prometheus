import re


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


def clean_paragraphs(text: str):

    raw_paragraphs = re.split(
        r"\n\s*\n",
        text
    )

    paragraphs = []

    for para in raw_paragraphs:

        para = re.sub(
            r"\s+",
            " ",
            para
        ).strip()

        if len(para) < 150:
            continue

        if is_mostly_numeric(para):
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

        chunks.append(
            "\n\n".join(
                current_chunk
            )
        )

    return chunks

def chunk_pages(pages):

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
                    "text": chunk
                }
            )

    return all_chunks