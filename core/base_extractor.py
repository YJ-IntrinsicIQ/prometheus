import json
import os

from core.context_paths import (
    discovery_path,
    extraction_path,
)
from knowledge.ai import get_llm
from knowledge.ai.input_packs import build_llm_input_pack, call_llm_with_input_pack
from knowledge.evidence_layer import (
    enrich_extracted_item,
    select_discovery_chunks,
    write_json,
)
from pipelines.pipeline_context import get_context

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional local dependency
    def load_dotenv():
        return False

load_dotenv()

# Backward-compatible attribute for older tests that monkeypatch the legacy client.
Groq = object


class BaseExtractor:
    def __init__(
        self,
        input_file,
        output_file,
        prompt,
        output_key,
        module_name=None,
        positive_patterns=None,
        negative_patterns=None,
        max_chunks=None,
        max_chars_per_chunk=None,
        max_total_chars=None,
        relevance_threshold=None,
    ):
        self.input_file = discovery_path(input_file)
        self.output_file = extraction_path(output_file)

        self.prompt = prompt
        self.output_key = output_key
        self.module_name = module_name or output_key
        self.positive_patterns = tuple(positive_patterns or ())
        self.negative_patterns = tuple(negative_patterns or ())
        self.max_chunks = max_chunks
        self.max_chars_per_chunk = max_chars_per_chunk
        self.max_total_chars = max_total_chars
        self.relevance_threshold = relevance_threshold
        self.llm = get_llm()
        self.model = getattr(self.llm, "model", "")
        self.max_batch_chars = 4000
        self.selection_metadata_path = self.output_file.with_name(
            f"{self.output_file.stem}_selection_metadata.json"
        )

    def _resolve_max_items_cap(self):
        raw_value = os.getenv("EXTRACTOR_MAX_ITEMS")
        if raw_value is None or not raw_value.strip():
            return None

        try:
            max_items = int(raw_value)
        except ValueError as exc:
            raise ValueError(
                "EXTRACTOR_MAX_ITEMS must be an integer when set"
            ) from exc

        if max_items <= 0:
            raise ValueError(
                "EXTRACTOR_MAX_ITEMS must be greater than 0 when set"
            )

        return max_items

    def extract(self, chunk_text):
        llm_input_pack = build_llm_input_pack(
            stage="extraction",
            purpose=f"Extract structured {self.output_key} items from discovery evidence.",
            company="",
            year=None,
            selected_input={
                "chunks": [
                    {
                        "chunk_id": "discovery_chunk_1",
                        "text": chunk_text,
                    }
                ]
            },
            observations=[
                {
                    "chunks": [
                        {
                            "chunk_id": "discovery_chunk_1",
                            "text": chunk_text,
                        }
                    ]
                }
            ],
            source_artifacts=[self.input_file.name],
            pack_name=f"{self.output_file.stem}_input_pack",
        )
        response = call_llm_with_input_pack(
            llm=self.llm,
            prompt=json.dumps(llm_input_pack, indent=2, ensure_ascii=False),
            input_pack=llm_input_pack,
            manifest_path=self.output_file.with_name(f"{self.output_file.stem}_llm_call_manifest.json"),
            require_source_artifacts=True,
            system_prompt=self.prompt,
            temperature=0,
            response_schema={"type": "object"},
        )
        content = response.text

        if not content or not content.strip():
            raise ValueError("Empty response from model")

        text = content.strip()

        if text.startswith("```"):
            text = text.removeprefix("```json")
            text = text.removeprefix("```")
            text = text.removesuffix("```").strip()

        return json.loads(text)

    def _split_oversized_part(self, part):
        if len(part) <= self.max_batch_chars:
            return [part]

        slices = []
        start = 0

        while start < len(part):
            end = min(
                start + self.max_batch_chars,
                len(part),
            )
            slices.append(
                part[start:end].strip()
            )
            start = end

        return [slice_text for slice_text in slices if slice_text]

    def _build_chunk_batches(self, chunk_text):
        text = (chunk_text or "").strip()
        if not text:
            return []

        if len(text) <= self.max_batch_chars:
            return [text]

        parts = [
            part.strip()
            for part in text.split("\n\n")
            if part.strip()
        ]
        if not parts:
            return self._split_oversized_part(text)

        batches = []
        current_batch = []
        current_length = 0

        for part in parts:
            for segment in self._split_oversized_part(part):
                separator_length = 2 if current_batch else 0
                projected_length = (
                    current_length
                    + separator_length
                    + len(segment)
                )

                if current_batch and projected_length > self.max_batch_chars:
                    batches.append(
                        "\n\n".join(current_batch)
                    )
                    current_batch = [segment]
                    current_length = len(segment)
                    continue

                current_batch.append(segment)
                current_length = projected_length

        if current_batch:
            batches.append(
                "\n\n".join(current_batch)
            )

        return batches or self._split_oversized_part(text)

    def run(self):
        with open(
            self.input_file,
            "r",
            encoding="utf-8",
        ) as f:
            chunks = json.load(f)

        total_input_items = len(chunks)
        max_items = self._resolve_max_items_cap()
        if max_items is not None and total_input_items > max_items:
            print(
                f"[EXTRACT] {self.input_file.name}: "
                f"total input items={total_input_items}, "
                f"capped to {max_items} for test run"
            )
            chunks = chunks[:max_items]

        selected_chunks, selection_metadata = select_discovery_chunks(
            chunks,
            module_name=self.module_name,
            positive_patterns=self.positive_patterns,
            negative_patterns=self.negative_patterns,
            max_chunks=self.max_chunks,
            max_chars_per_chunk=self.max_chars_per_chunk,
            max_total_chars=self.max_total_chars,
            relevance_threshold=self.relevance_threshold,
        )
        write_json(self.selection_metadata_path, selection_metadata)

        extracted_items = []
        context = get_context()
        source_year = getattr(context, "year", "") if context is not None else ""
        chunk_batches = []
        for item_index, item in enumerate(selected_chunks):
            item_batches = self._build_chunk_batches(
                item.get("chunk", "")
            )
            for batch_index, chunk_text in enumerate(
                item_batches,
                start=1,
            ):
                chunk_batches.append(
                    {
                        "item_index": item_index,
                        "item_count": len(item_batches),
                        "item": item,
                        "chunk_text": chunk_text,
                        "item_batch_index": batch_index,
                    }
                )

        print(
            f"[EXTRACT] {self.input_file.name}: "
            f"total input items={total_input_items}, "
            f"items processed={len(selected_chunks)}, "
            f"total batches={len(chunk_batches)}"
        )

        for batch_number, batch in enumerate(
            chunk_batches,
            start=1,
        ):
            item = batch["item"]
            print(
                f"[EXTRACT] batch {batch_number}/{len(chunk_batches)} "
                f"(item {batch['item_index'] + 1}/{len(selected_chunks)}, "
                f"part {batch['item_batch_index']}/{batch['item_count']})"
            )

            try:
                result = self.extract(
                    batch["chunk_text"]
                )
            except Exception as exc:
                raise RuntimeError(
                    f"Extraction failed for {self.input_file.name} "
                    f"at batch {batch_number}/{len(chunk_batches)} "
                    f"(item {batch['item_index'] + 1}/{len(selected_chunks)}, "
                    f"part {batch['item_batch_index']}/{batch['item_count']}, "
                    f"page={item.get('page')})"
                ) from exc

            items = result.get(
                self.output_key,
                [],
            )

            for extracted_item in items:
                extracted_item["source_chunk"] = (
                    item["chunk"]
                )
                extracted_item["page"] = item.get("page")
                extracted_item["distance"] = item.get("distance")
                if source_year and not extracted_item.get("source_year"):
                    extracted_item["source_year"] = source_year
                enriched_item = enrich_extracted_item(
                    extracted_item,
                    module_name=self.module_name,
                    item_index=len(extracted_items) + 1,
                    selection_metadata=item.get("selection_metadata"),
                )
                extracted_items.append(
                    enriched_item
                )

        with open(
            self.output_file,
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(
                extracted_items,
                f,
                indent=2,
                ensure_ascii=False,
            )

        return extracted_items
