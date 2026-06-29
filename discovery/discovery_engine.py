import chromadb

from core.document_registry import metadata_filter
from embeddings.search import search_chunks


def semantic_discovery(
    queries,
    company=None,
    year=None,
    document_type=None,
    distance_threshold=1.1,
    n_results=2
):

    discovered = {}

    for query in queries:

        results = search_chunks(
            query=query,
            company=company,
            year=year,
            document_type=document_type,
            n_results=n_results
        )

        docs = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]

        for doc, metadata, distance in zip(
            docs,
            metadatas,
            distances
        ):

            if distance > distance_threshold:
                continue

            if doc not in discovered:

                discovered[doc] = {
                    "chunk": doc,
                    "page": metadata.get("page"),
                    "distance": distance,
                    "matched_queries": []
                }

            discovered[doc]["matched_queries"].append(
                query
            )

    return discovered


def keyword_discovery(
    chroma_path,
    positive_patterns,
    negative_patterns,
    company=None,
    year=None,
    document_type=None,
):

    client = chromadb.PersistentClient(
        path=str(chroma_path)
    )

    collection = client.get_collection(
        "company_documents"
    )

    where = metadata_filter(
        company=company,
        year=year,
        document_type=document_type,
    )

    get_kwargs = {
        "include": [
            "documents",
            "metadatas"
        ]
    }

    if where:
        get_kwargs["where"] = where

    data = collection.get(
        **get_kwargs
    )

    discovered = {}

    for doc, metadata in zip(
        data["documents"],
        data["metadatas"]
    ):

        text = doc.lower()

        if any(
            pattern in text
            for pattern in negative_patterns
        ):
            continue

        matches = []

        for pattern in positive_patterns:

            if pattern in text:
                matches.append(pattern)

        if not matches:
            continue

        discovered[doc] = {
            "chunk": doc,
            "page": metadata.get("page"),
            "matched_keywords": matches
        }

    return discovered


def merge_results(
    semantic_results,
    keyword_results
):

    merged = {}

    for doc, data in semantic_results.items():

        merged[doc] = data

    for doc, data in keyword_results.items():

        if doc not in merged:

            merged[doc] = data

        else:

            merged[doc][
                "matched_keywords"
            ] = data.get(
                "matched_keywords",
                []
            )

    return list(
        merged.values()
    )
