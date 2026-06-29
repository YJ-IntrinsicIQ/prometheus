import json
import os
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

from core.context_paths import (
    discovery_path,
    extraction_path,
)

load_dotenv()


class BaseExtractor:
    def __init__(
        self,
        input_file,
        output_file,
        prompt,
        output_key,
    ):
        self.input_file = discovery_path(input_file)
        self.output_file = extraction_path(output_file)

        self.prompt = prompt
        self.output_key = output_key
        self.client = Groq(
            api_key=os.getenv("GROQ_API_KEY")
        )

    def extract(self, chunk_text):
        response = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": self.prompt,
                },
                {
                    "role": "user",
                    "content": chunk_text,
                },
            ],
        )

        content = response.choices[0].message.content

        if not content or not content.strip():
            raise ValueError("Empty response from model")

        text = content.strip()

        if text.startswith("```"):
            text = text.removeprefix("```json")
            text = text.removeprefix("```")
            text = text.removesuffix("```").strip()

        return json.loads(text)

    def run(self):
        with open(
            self.input_file,
            "r",
            encoding="utf-8",
        ) as f:
            chunks = json.load(f)

        extracted_items = []

        for item in chunks:
            result = self.extract(
                item["chunk"]
            )

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

                extracted_items.append(
                    extracted_item
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
