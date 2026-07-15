from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_REAL_INTELLIGENCE_DIR = _TESTS_DIR.parents[1] / "intelligence"

__path__ = [str(_REAL_INTELLIGENCE_DIR), str(_TESTS_DIR)]
