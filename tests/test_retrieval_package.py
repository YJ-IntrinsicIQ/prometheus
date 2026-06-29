from pathlib import Path

from knowledge.retrieval import HybridRetriever, load_chunks_from_outputs, validate_retrieval_result


def test_load_chunks_from_outputs():
    chunks = load_chunks_from_outputs(Path("outputs"))
    assert chunks
    assert all("text" in chunk and "metadata" in chunk for chunk in chunks)


def test_retriever_returns_results():
    retriever = HybridRetriever(persist_directory="/tmp/finance-retrieval-test")
    result = retriever.search("sustainability energy efficiency", top_k=5)
    validate_retrieval_result(result)
    assert result.chunks
    assert len(result.chunks) <= 5
