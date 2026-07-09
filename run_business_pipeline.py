import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("HF_HOME", str(ROOT / "hf_cache"))
os.environ.setdefault("TRANSFORMERS_CACHE", str(ROOT / "hf_cache"))
os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(ROOT / "hf_cache"))

from core.company_context import CompanyContext
from knowledge.business_blueprint import BusinessBlueprint
from knowledge.business_classifier import BusinessClassifier
from knowledge.business_interpreter import BusinessInterpreter
from knowledge.ai import get_llm
from knowledge.company_memory import CompanyMemoryBuilder, save_company_memory
from knowledge.discovery_runtime import DiscoveryRuntime
from knowledge.question_engine import QuestionPlanner
from knowledge.retrieval.retriever import HybridRetriever
from pipelines.pipeline_context import set_context
from scripts.pdf_reader import extract_pages
from scripts.smart_chunker import chunk_pages


class OneShotRetriever:
    def __init__(self, retriever):
        self._retriever = retriever
        self._built = False

    def build_company_index(self, company: str, year: str):
        if self._built:
            return None
        self._built = True
        return self._retriever.build_company_index(company=company, year=year)

    def retrieve(self, query: str, top_k: int = 10):
        return self._retriever.retrieve(query=query, top_k=top_k)

    def search(self, query: str, top_k: int = 10):
        return self._retriever.search(query=query, top_k=top_k)


def _build_document_payload(raw_document_path: Path, company: str, year: str) -> dict:
    return {
        "company_id": company,
        "entities": [
            {
                "name": company.title(),
                "entity_type": "company",
                "events": [
                    {
                        "event_type": "document_loaded",
                        "summary": f"Loaded {raw_document_path.name}",
                        "evidence": [
                            {
                                "source": raw_document_path.name,
                                "source_type": "annual_report",
                                "content": f"Processed {raw_document_path.name}",
                            }
                        ],
                    }
                ],
            }
        ],
        "metadata": {
            "company": company,
            "year": year,
            "source_path": str(raw_document_path),
        },
    }


def _build_blueprint(company_memory, company: str) -> BusinessBlueprint:
    llm = get_llm()

    def ai_adapter(prompt: str) -> str:
        response = llm.generate(
            prompt=prompt,
            response_schema={"type": "object"},
        )
        print(f"AI Provider: {response.provider}")
        print(f"AI Model: {response.model}")
        print(f"AI Latency: {response.latency_ms:.2f}ms")
        print(f"AI Prompt tokens: {response.prompt_tokens}")
        print(f"AI Completion tokens: {response.completion_tokens}")
        print(f"AI Total tokens: {response.total_tokens}")
        return response.text

    interpreter = BusinessInterpreter(company_memory, llm_client=ai_adapter)
    return interpreter.interpret()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _resolve_company_year(company: str, year: str) -> tuple[str, str]:
    normalized_company = company.strip().lower()
    normalized_year = year.strip().lower()
    if normalized_year.startswith("fy") and len(normalized_year) > 2:
        normalized_year = normalized_year[2:]
    if len(normalized_year) == 2 and normalized_year.isdigit():
        normalized_year = f"20{normalized_year}"
    return normalized_company, normalized_year


def _resolve_raw_document_path(company: str, year: str, raw_document_path=None) -> Path:
    if raw_document_path:
        candidate = Path(raw_document_path).expanduser().resolve()
        if candidate.exists():
            return candidate

    default_candidates = [
        Path("data/annual_reports") / f"{company}_fy{year[-2:]}.pdf",
        Path("data/annual_reports") / f"{company}_fy{year[-2:]}.txt",
        Path("data/annual_reports") / f"{company}_{year}.pdf",
        Path("data/annual_reports") / f"{company}_{year}.txt",
    ]
    for candidate in default_candidates:
        if candidate.exists():
            return candidate.resolve()
    return Path(raw_document_path).expanduser().resolve() if raw_document_path else Path("data/annual_reports") / f"{company}_fy{year[-2:]}.pdf"


def run_business_pipeline(company: str, year: str, raw_document_path=None):
    company, year = _resolve_company_year(company, year)
    raw_path = _resolve_raw_document_path(company, year, raw_document_path)
    if not raw_path.exists():
        raise FileNotFoundError(f"Raw document not found: {raw_path}")

    context = CompanyContext(company=company, year=year)
    context.create_directories()
    set_context(context)

    pages = extract_pages(raw_path)
    chunk_output_path = context.extracted_dir / "clean_chunks.json"
    chunks = chunk_pages(
        pages,
        company=company,
        year=year,
        document_type="annual_report",
        output_path=chunk_output_path,
    )

    document_payload = _build_document_payload(raw_path, company, year)
    company_memory = CompanyMemoryBuilder(existing_memory=None, new_document=document_payload).build()
    business_blueprint = _build_blueprint(company_memory, company)
    business_classification = BusinessClassifier().classify(business_blueprint)

    memory_path = context.intelligence_dir / "company_memory.json"
    blueprint_path = context.intelligence_dir / "business_blueprint.json"
    classification_path = context.intelligence_dir / "business_classification.json"
    save_company_memory(company_memory, memory_path)
    _write_json(blueprint_path, business_blueprint.to_dict())
    _write_json(classification_path, business_classification)

    retriever = OneShotRetriever(HybridRetriever())
    retriever.build_company_index(company=company, year=year)

    planner = QuestionPlanner()
    plan = planner.build_plan(business_classification)

    runtime = DiscoveryRuntime(retriever=retriever)
    started_at = time.time()
    result = runtime.run(plan, business_classification={
        "company": company,
        "year": year,
        **business_classification,
    })

    discovery_plan_path = context.intelligence_dir / "discovery_plan.json"
    module_results_path = context.intelligence_dir / "module_results.json"
    discovery_runtime_path = context.intelligence_dir / "discovery_runtime.json"

    _write_json(discovery_plan_path, plan.to_dict())
    _write_json(module_results_path, {"module_results": [item.to_dict() for item in result.module_results]})
    _write_json(discovery_runtime_path, result.to_dict())

    print(f"Chunk count: {len(chunks)}")
    print(f"Business DNAs: {', '.join(business_classification.get('business_dnas', [])) or 'None'}")
    print(f"Modules loaded: {len(plan.loaded_modules)}")
    print(f"Retrieved chunks: {result.statistics.retrieved_chunks}")
    print(f"LLM calls: {result.statistics.llm_calls}")
    print(f"Questions answered: {result.statistics.questions_answered}")
    print(f"Execution time: {time.time() - started_at:.3f}s")

    return {
        "clean_chunks_path": chunk_output_path,
        "company_memory_path": memory_path,
        "business_blueprint_path": blueprint_path,
        "business_classification_path": classification_path,
        "discovery_plan_path": discovery_plan_path,
        "module_results_path": module_results_path,
        "discovery_runtime_path": discovery_runtime_path,
        "result": result,
    }


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("company")
    parser.add_argument("year")
    parser.add_argument("raw_document_path", nargs="?", default=None)
    return parser


def main():
    args = build_parser().parse_args()
    run_business_pipeline(args.company, args.year, args.raw_document_path)


if __name__ == "__main__":
    main()
