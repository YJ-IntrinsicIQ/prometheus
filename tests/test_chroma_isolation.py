"""The repository's chroma_db/ must be unmodifiable by tests (see tests/conftest.py)."""
import hashlib
from pathlib import Path

import pytest

REAL = Path(__file__).resolve().parents[1] / "chroma_db"


def _digest():
    return hashlib.sha256((REAL / "chroma.sqlite3").read_bytes()).hexdigest()


@pytest.mark.skipif(not (REAL / "chroma.sqlite3").exists(), reason="no repository index")
def test_writes_through_the_repository_path_land_in_a_private_copy():
    chromadb = pytest.importorskip("chromadb")
    before = _digest()
    client = chromadb.PersistentClient(path=str(REAL))
    client.get_or_create_collection("isolation_probe").add(ids=["probe"], documents=["probe"], embeddings=[[0.0, 0.1, 0.2]])
    del client
    assert _digest() == before
