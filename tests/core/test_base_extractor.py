import json
import sys
import types

import pytest

from core.company_context import CompanyContext
from pipelines.pipeline_context import set_context

dotenv_stub = types.ModuleType("dotenv")
dotenv_stub.load_dotenv = lambda *args, **kwargs: None
sys.modules.setdefault("dotenv", dotenv_stub)

groq_stub = types.ModuleType("groq")
groq_stub.Groq = object
sys.modules.setdefault("groq", groq_stub)

from core.base_extractor import BaseExtractor


class DummyGroqClient:
    def __init__(self, *args, **kwargs):
        self.chat = self
        self.completions = self

    def create(self, *args, **kwargs):
        raise AssertionError("Tests should override BaseExtractor.extract")


class RecordingExtractor(BaseExtractor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = []

    def extract(self, chunk_text):
        self.calls.append(chunk_text)
        return {
            "items": [
                {
                    "value": chunk_text,
                }
            ]
        }


class FailingExtractor(BaseExtractor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = 0

    def extract(self, chunk_text):
        self.calls += 1
        if self.calls == 2:
            raise ValueError("model exploded")
        return {"items": []}


@pytest.fixture
def extractor_paths(tmp_path, monkeypatch):
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "output.json"

    monkeypatch.setattr(
        "core.base_extractor.discovery_path",
        lambda path: input_path,
    )
    monkeypatch.setattr(
        "core.base_extractor.extraction_path",
        lambda path: output_path,
    )
    monkeypatch.setattr(
        "core.base_extractor.Groq",
        DummyGroqClient,
    )

    return input_path, output_path


def test_base_extractor_batches_oversized_chunk_and_preserves_output_shape(extractor_paths):
    input_path, output_path = extractor_paths
    chunk_text = "alpha\n\nbeta\n\ngamma"
    input_path.write_text(
        json.dumps(
            [
                {
                    "chunk": chunk_text,
                    "page": 7,
                    "distance": 0.42,
                }
            ]
        ),
        encoding="utf-8",
    )

    extractor = RecordingExtractor(
        input_file="input.json",
        output_file="output.json",
        prompt="prompt",
        output_key="items",
    )
    extractor.max_batch_chars = 10

    result = extractor.run()

    assert extractor.calls == ["alpha", "beta", "gamma"]
    assert [item["value"] for item in result] == ["alpha", "beta", "gamma"]
    assert all(item["source_chunk"] == chunk_text for item in result)
    assert all(item["page"] == 7 for item in result)
    assert all(item["distance"] == 0.42 for item in result)
    assert json.loads(output_path.read_text(encoding="utf-8")) == result


def test_base_extractor_raises_clear_error_with_batch_context(extractor_paths):
    input_path, _ = extractor_paths
    input_path.write_text(
        json.dumps(
            [
                {
                    "chunk": "alpha\n\nbeta\n\ngamma",
                    "page": 11,
                }
            ]
        ),
        encoding="utf-8",
    )

    extractor = FailingExtractor(
        input_file="input.json",
        output_file="output.json",
        prompt="prompt",
        output_key="items",
    )
    extractor.max_batch_chars = 10

    with pytest.raises(RuntimeError) as excinfo:
        extractor.run()

    assert "batch 2/3" in str(excinfo.value)
    assert "item 1/1" in str(excinfo.value)
    assert "part 2/3" in str(excinfo.value)
    assert "page=11" in str(excinfo.value)


def test_base_extractor_caps_input_items_when_env_is_set(extractor_paths, monkeypatch, capsys):
    input_path, output_path = extractor_paths
    input_path.write_text(
        json.dumps(
            [
                {"chunk": "alpha", "page": 1, "distance": 0.1},
                {"chunk": "beta", "page": 2, "distance": 0.2},
                {"chunk": "gamma", "page": 3, "distance": 0.3},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EXTRACTOR_MAX_ITEMS", "2")

    extractor = RecordingExtractor(
        input_file="input.json",
        output_file="output.json",
        prompt="prompt",
        output_key="items",
    )

    result = extractor.run()
    captured = capsys.readouterr()

    assert extractor.calls == ["alpha", "beta"]
    assert [item["value"] for item in result] == ["alpha", "beta"]
    assert "total input items=3, capped to 2 for test run" in captured.out
    assert "total input items=3, items processed=2, total batches=2" in captured.out
    assert json.loads(output_path.read_text(encoding="utf-8")) == result


def test_base_extractor_stamps_context_year_as_source_year(extractor_paths):
    input_path, _ = extractor_paths
    input_path.write_text(
        json.dumps(
            [
                {"chunk": "alpha", "page": 1, "distance": 0.1},
            ]
        ),
        encoding="utf-8",
    )

    context = CompanyContext(company="tanla", year="fy20")
    set_context(context)
    try:
        extractor = RecordingExtractor(
            input_file="input.json",
            output_file="output.json",
            prompt="prompt",
            output_key="items",
        )

        result = extractor.run()

        assert result[0]["source_year"] == "fy20"
    finally:
        set_context(None)


@pytest.mark.parametrize("value", ["0", "-1", "abc"])
def test_base_extractor_rejects_invalid_max_items_env(extractor_paths, monkeypatch, value):
    input_path, _ = extractor_paths
    input_path.write_text(
        json.dumps(
            [
                {"chunk": "alpha", "page": 1},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EXTRACTOR_MAX_ITEMS", value)

    extractor = RecordingExtractor(
        input_file="input.json",
        output_file="output.json",
        prompt="prompt",
        output_key="items",
    )

    with pytest.raises(ValueError, match="EXTRACTOR_MAX_ITEMS"):
        extractor.run()
