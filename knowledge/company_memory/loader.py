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


def save_company_memory(memory: CompanyMemory, path: Union[str, Path], output_root: Union[str, Path, None] = None) -> Path:
    from core.context_paths import guarded_write_or_refuse_served

    path = Path(path)
    guarded_write_or_refuse_served(path, json.dumps(memory.to_dict(), indent=2, ensure_ascii=False), output_root)
    return path
