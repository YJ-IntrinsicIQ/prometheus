import json
from pathlib import Path

from core.company_context import CompanyContext
from pipelines.pipeline_context import set_context
from scripts.pdf_reader import extract_pages
from scripts.smart_chunker import chunk_pages

for company, year in [('polymatech', '2025'), ('tips', '2024')]:
    context = CompanyContext(company=company, year=year)
    context.create_directories()
    set_context(context)
    from core.inbox_paths import PROCESSED
    _fy = 'fy%s' % str(year)[-2:]
    _processed = PROCESSED / company / _fy / 'annual_report'
    pdf_path = next(
        (p for p in sorted(_processed.glob('*.pdf')) if _processed.exists()), None
    )
    if not pdf_path.exists():
        print('%s/%s: SKIP %s' % (company, year, pdf_path))
        continue
    pages = extract_pages(pdf_path)
    chunks = chunk_pages(
        pages,
        company=company,
        year=year,
        document_type='annual_report',
        output_path=context.extracted_dir / 'clean_chunks.json',
    )
    artifact = context.extracted_dir / 'clean_chunks.json'
    print('%s/%s: chunks=%s artifact_exists=%s' % (company, year, len(chunks), artifact.exists()))
    if artifact.exists():
        payload = json.loads(artifact.read_text(encoding='utf-8'))
        print('  chunk_count=%s first_chunk_id=%s' % (payload['chunk_count'], payload['chunks'][0]['chunk_id'] if payload['chunks'] else None))
