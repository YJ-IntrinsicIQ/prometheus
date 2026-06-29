from pathlib import Path

from pipelines.pipeline_context import get_context


ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = ROOT / "outputs"


def resolve_path(path, context_dir=None):
    context = get_context()
    path = Path(path)

    if context and context_dir:
        directory = getattr(context, context_dir)
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )
        return directory / path.name

    if path.is_absolute():
        return path

    if path.parts and path.parts[0] == "outputs":
        return ROOT / path

    if len(path.parts) == 1:
        return OUTPUTS_DIR / path.name

    return ROOT / path


def discovery_path(path, context_dir=None):
    return resolve_path(
        path,
        context_dir or "discovery_dir",
    )


def extraction_path(path, context_dir=None):
    return resolve_path(
        path,
        context_dir or "extraction_dir",
    )


def intelligence_path(path, context_dir=None):
    return resolve_path(
        path,
        context_dir or "intelligence_dir",
    )
