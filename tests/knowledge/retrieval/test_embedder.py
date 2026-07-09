from knowledge.retrieval import embedder


def test_load_embedding_model_prefers_cached_snapshot(tmp_path, monkeypatch):
    cache_dir = tmp_path / "hf_cache"
    model_cache_dir = cache_dir / "hub" / "models--sentence-transformers--all-MiniLM-L6-v2"
    snapshot_path = model_cache_dir / "snapshots" / "rev-123"
    snapshot_path.mkdir(parents=True, exist_ok=True)
    (model_cache_dir / "refs").mkdir(parents=True, exist_ok=True)
    (model_cache_dir / "refs" / "main").write_text("rev-123", encoding="utf-8")

    seen = {}

    class FakeModel:
        pass

    def fake_sentence_transformer(model_path, cache_folder=None, local_files_only=False):
        seen["model_path"] = model_path
        seen["cache_folder"] = cache_folder
        seen["local_files_only"] = local_files_only
        return FakeModel()

    monkeypatch.setattr(embedder, "_MODEL", None)
    monkeypatch.setattr(embedder, "CACHE_PATH", cache_dir)
    monkeypatch.setattr(embedder, "MODEL_CACHE_DIR", model_cache_dir)
    monkeypatch.setattr(embedder, "MODEL_REF", model_cache_dir / "refs" / "main")
    monkeypatch.setattr(embedder, "SentenceTransformer", fake_sentence_transformer)

    model = embedder.load_embedding_model()

    assert isinstance(model, FakeModel)
    assert seen == {
        "model_path": str(snapshot_path),
        "cache_folder": str(cache_dir),
        "local_files_only": True,
    }


def test_embed_texts_uses_model_output_lists(monkeypatch):
    class FakeEmbeddings:
        def tolist(self):
            return [[0.1, 0.2], [0.3, 0.4]]

    class FakeModel:
        def encode(self, texts, convert_to_numpy=True, normalize_embeddings=True):
            assert texts == ["alpha", "beta"]
            assert convert_to_numpy is True
            assert normalize_embeddings is True
            return FakeEmbeddings()

    monkeypatch.setattr(embedder, "load_embedding_model", lambda: FakeModel())
    monkeypatch.setattr(embedder, "SentenceTransformer", object())

    assert embedder.embed_texts(["alpha", "beta"]) == [[0.1, 0.2], [0.3, 0.4]]


def test_embed_texts_falls_back_when_sentence_transformers_missing(monkeypatch):
    monkeypatch.setattr(embedder, "SentenceTransformer", None)

    vectors = embedder.embed_texts(["alpha beta", "beta gamma"])

    assert len(vectors) == 2
    assert all(isinstance(value, float) for row in vectors for value in row)
    assert len(vectors[0]) == len(vectors[1])
