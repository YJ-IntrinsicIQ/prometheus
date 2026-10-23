"""Suite-wide isolation: the pipeline's active context is process-global state, so it is cleared around every test; a context left behind by one test must never
decide the company-data root of the next."""
import pytest


@pytest.fixture(autouse=True)
def _reset_active_pipeline_context():
    from pipelines import pipeline_context

    pipeline_context.set_context(None)
    yield
    pipeline_context.set_context(None)


@pytest.fixture(scope="session", autouse=True)
def _isolate_repository_chroma_db(tmp_path_factory):
    """No test may modify the repository's Chroma index (`chroma_db/`): the first client opened on that directory (or any path inside it) is redirected to a private
    copy made for this test session. Tests that read the index still see its content; their writes land in the copy."""
    import shutil
    from pathlib import Path

    try:
        import chromadb
    except Exception:       # chromadb unavailable: nothing can write to it
        yield
        return
    real = (Path(__file__).resolve().parents[1] / "chroma_db").resolve()
    original, copy = chromadb.PersistentClient, {}

    def isolated_client(path=".", *args, **kwargs):
        target = Path(path).resolve()
        if target == real or real in target.parents:
            if "root" not in copy:
                copy["root"] = tmp_path_factory.mktemp("chroma_copy") / "chroma_db"
                shutil.copytree(real, copy["root"])
            path = str(copy["root"] / target.relative_to(real))
        return original(path, *args, **kwargs)

    chromadb.PersistentClient = isolated_client
    try:
        yield
    finally:
        chromadb.PersistentClient = original
