import json
from pathlib import Path
from typing import Optional, Union

from .schema import CompanyMemory


def load_company_memory(path: Union[str, Path]) -> Optional[CompanyMemory]:
    path = Path(path)
    if not path.exists():
        return None

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    return CompanyMemory.from_dict(payload)


def save_company_memory(memory: CompanyMemory, path: Union[str, Path]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:
        json.dump(memory.to_dict(), handle, indent=2, ensure_ascii=False)

    return path
