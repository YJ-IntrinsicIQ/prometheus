import fitz


def extract_pages(pdf_path: str):

    doc = fitz.open(pdf_path)

    pages = []

    for page_num, page in enumerate(doc, start=1):

        pages.append(
            {
                "page": page_num,
                "text": page.get_text()
            }
        )

    doc.close()

    return pages