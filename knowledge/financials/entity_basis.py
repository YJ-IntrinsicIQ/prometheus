"""The reporting basis a filing presents, read from the filing's own declaration.

A table-level "consolidated" signal ("Total consolidated assets as per published financial statements" in a bank's capital-adequacy disclosure) says nothing about which statements the
report contains. A report that declares "These standalone financial statements have been prepared..." or "there is no requirement to prepare consolidated financial statements" presents
ONE set of statements, and every figure taken from it is on that basis. Both declarations present, or neither: the basis is not settled here ("both" / "unknown") and nothing is relabelled.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

DECLARES_STANDALONE = re.compile(r"\bthese\s+standalone\s+(?:ind\s*as\s+)?financial\s+statements|\bstandalone\s+(?:ind\s*as\s+)?financial\s+statements\s+of\s+the\s+(?:company|bank)|"
                                 r"no\s+requirement\s+to\s+prepare\s+consolidated|does\s+not\s+have\s+any\s+subsidiar", re.I)
DECLARES_CONSOLIDATED = re.compile(r"\bthese\s+consolidated\s+(?:ind\s*as\s+)?financial\s+statements|\bconsolidated\s+financial\s+statements\s+of\s+the\s+(?:group|company)", re.I)


def basis_from_text(text: str) -> str:
    standalone, consolidated = bool(DECLARES_STANDALONE.search(text)), bool(DECLARES_CONSOLIDATED.search(text))
    return "both" if standalone and consolidated else "standalone" if standalone else "consolidated" if consolidated else "unknown"


def declared_entity_basis(chunk_paths: Iterable[Path]) -> str:
    texts = []
    for path in chunk_paths:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        chunks = payload.get("chunks") if isinstance(payload, dict) else payload
        texts.extend(str(c.get("text") or c.get("content") or "") if isinstance(c, dict) else str(c) for c in chunks or [])
    return basis_from_text(" ".join(texts))
