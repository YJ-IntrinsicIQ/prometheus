from knowledge.retrieval.indexer import ChunkIndexer


def test_clear_ignores_missing_collection(monkeypatch, tmp_path):
    indexer = ChunkIndexer.__new__(ChunkIndexer)
    indexer.persist_directory = tmp_path

    class NotFoundError(Exception):
        pass

    class FakeClient:
        def __init__(self):
            self.deleted = []
            self.created = []

        def delete_collection(self, name):
            self.deleted.append(name)
            raise NotFoundError("missing")

        def get_or_create_collection(self, name):
            self.created.append(name)
            return {"name": name}

    client = FakeClient()
    indexer.client = client
    indexer.collection = {"name": "old"}

    monkeypatch.setattr("knowledge.retrieval.indexer.COLLECTION_NAME", "company_documents")

    indexer.clear()

    assert client.deleted == ["company_documents"]
    assert client.created == ["company_documents"]
    assert indexer.collection == {"name": "company_documents"}


def test_index_chunks_recreates_collection_when_add_hits_missing_collection(monkeypatch, tmp_path):
    indexer = ChunkIndexer.__new__(ChunkIndexer)
    indexer.persist_directory = tmp_path

    class NotFoundError(Exception):
        pass

    class FakeCollection:
        def __init__(self, fail_once=False):
            self.fail_once = fail_once
            self.add_calls = 0

        def add(self, embeddings, documents, metadatas, ids):
            self.add_calls += 1
            if self.fail_once:
                self.fail_once = False
                raise NotFoundError("missing")

    class FakeClient:
        def __init__(self):
            self.created = []
            self.second_collection = FakeCollection()

        def get_or_create_collection(self, name):
            self.created.append(name)
            return self.second_collection

    first_collection = FakeCollection(fail_once=True)
    client = FakeClient()
    indexer.client = client
    indexer.collection = first_collection

    monkeypatch.setattr("knowledge.retrieval.indexer.COLLECTION_NAME", "company_documents")
    monkeypatch.setattr("knowledge.retrieval.indexer.embed_texts", lambda texts: [[0.1, 0.2] for _ in texts])

    ids = indexer.index_chunks(
        [
            {"text": "alpha", "metadata": {"page": 1}},
            {"text": "beta", "metadata": {"page": 2}},
        ]
    )

    assert ids == ["chunk-0", "chunk-1"]
    assert client.created == ["company_documents"]
    assert indexer.collection is client.second_collection
    assert first_collection.add_calls == 1
    assert client.second_collection.add_calls == 1
