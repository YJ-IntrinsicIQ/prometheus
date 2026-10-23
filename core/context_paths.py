import contextlib
import os
import sys
import tempfile
from pathlib import Path

from pipelines.pipeline_context import get_context


ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = ROOT / "outputs"


def resolve_path(path, context_dir=None):
    context = get_context()
    path = Path(path)

    if context and context_dir:
        # A stage's files live under the active context's EXPLICIT root. The directory is resolved (symlinks included) and must stay inside that root.
        root = getattr(context, "companies_root", None)
        directory = getattr(context, context_dir)
        if root is not None:
            directory = safe_destination(root, directory)
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )
        return safe_destination(root, directory / path.name) if root is not None else directory / path.name

    if path.is_absolute():
        resolved = path
    elif path.parts and path.parts[0] == "outputs":
        resolved = ROOT / path
    elif len(path.parts) == 1:
        resolved = OUTPUTS_DIR / path.name
    else:
        resolved = ROOT / path

    # No active context: this repo-level fallback never reaches company data. A path that lands in the served tree is refused rather than silently served.
    if _touches_served_file(resolved):
        raise WriteBoundaryError(f"no active company context: refusing the implicit path {resolved}, which is inside the served company tree")
    return resolved


def _touches_served_file(resolved) -> bool:
    try:
        real = Path(os.path.realpath(os.fspath(resolved)))
    except (TypeError, ValueError):
        return False
    served = served_companies_root()
    return real == served or served in real.parents


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


# ── Output-boundary guard (P0 write safety) ──
# The served company tree is fixed by where this file lives, never by the working directory. Every builder that writes company intelligence resolves an explicit,
# absolute output root through resolve_output_root and every destination through safe_destination / guarded_write_text, so a scratch run cannot reach served data.
SERVED_COMPANIES_ROOT = ROOT / "companies"


class WriteBoundaryError(PermissionError):
    """A write was refused because its destination could not be proven to lie inside an authorized output root."""


def served_companies_root() -> Path:
    return SERVED_COMPANIES_ROOT.resolve()


def _touches_served(resolved: Path) -> bool:
    served = served_companies_root()
    return resolved == served or served in resolved.parents or resolved in served.parents


def resolve_output_root(root, *, authorize_served: bool = False) -> Path:
    """The explicit output root: required, absolute, symlinks resolved. A root that is, lies inside or contains the served companies/ tree is refused unless the
    caller passes authorize_served=True (the human-initiated pipeline does; scratch runs and tools never should)."""
    if root is None or str(root) == "":
        raise WriteBoundaryError("an explicit output root is required; there is no default and no fallback to companies/")
    path = Path(root)
    if not path.is_absolute():
        raise WriteBoundaryError(f"the output root must be an absolute path, got {str(root)!r}")
    resolved = path.resolve()
    if _touches_served(resolved) and not authorize_served:
        raise WriteBoundaryError(f"{resolved} is, or contains, the served company tree; writing there needs authorize_served=True")
    return resolved


def safe_destination(root, destination) -> Path:
    """Resolve a destination (absolute, or relative to root) with symlinks and '..' collapsed, and require it to lie inside the resolved root."""
    base = Path(root).resolve()
    candidate = Path(destination)
    candidate = candidate if candidate.is_absolute() else base / candidate
    resolved = Path(os.path.realpath(candidate))
    if resolved != base and base not in resolved.parents:
        raise WriteBoundaryError(f"destination {resolved} escapes the authorized output root {base}")
    return resolved


_POST_WRITE_HOOKS: list = []


def register_post_write_hook(hook) -> None:
    """hook(root, path) runs after every guarded write. A hook never fails a write: what it could not record stays unrecorded (and so unusable) rather than breaking the writer."""
    if hook not in _POST_WRITE_HOOKS:
        _POST_WRITE_HOOKS.append(hook)


def guarded_write_text(root, destination, text: str, *, force: bool = True) -> Path:
    """Atomic text write whose destination is proven inside root before anything is created. The temporary file lives in the destination directory."""
    path = safe_destination(root, destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_destination(root, path)                      # re-check after mkdir: a directory created or swapped meanwhile must not redirect the write
    if path.exists() and not force:
        return path
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp") as handle:
        handle.write(text)
        temp_path = Path(handle.name)
    temp_path.replace(path)
    for hook in _POST_WRITE_HOOKS:
        try:
            hook(root, path)
        except Exception:                              # noqa: BLE001 - see register_post_write_hook
            pass
    return path


def planned_writes(root, *destinations) -> dict:
    """Dry-run: the exact absolute files a writer would create, each proven inside root. Read-only."""
    base = Path(root).resolve()
    return {Path(d).name: safe_destination(base, d) for d in destinations}


def logical_company_path(path, companies_root) -> str:
    """How a manifest records where a file lives: companies/<slug>/... , independent of the absolute root a run used (so output bytes do not depend on the root)."""
    try:
        return str(Path("companies") / Path(path).relative_to(Path(companies_root)))
    except ValueError:
        return str(path)


# ── Process-wide backstop: the served tree is default-deny ──
# Per-builder roots are the primary boundary. This audit hook is the fail-closed net under everything else (financial stage writers, synthesis generators, scripts,
# tests, future code): any file write, create, rename, delete or copy whose destination resolves into the served companies/ tree is refused unless the process was
# explicitly authorized (the pipeline's --authorize-served-write or `with authorize_served_writes():`). It is installed on import and
# cannot be removed (CPython audit hooks are permanent); only the authorization state can change.
_SERVED_WRITES_AUTHORIZED = False
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
_DESTINATION_ONLY_EVENTS = {"os.symlink", "os.link", "shutil.copyfile", "shutil.copymode", "shutil.copystat", "shutil.copytree"}
_PATH_EVENTS = {"os.mkdir", "os.rmdir", "os.remove", "os.rename", "os.truncate", "os.symlink", "os.link", "shutil.copyfile", "shutil.copymode", "shutil.copystat",
                "shutil.copytree", "shutil.move", "shutil.rmtree", "os.chmod"}


def served_writes_authorized() -> bool:
    # an environment variable alone never authorizes served writes: authorization is an in-process, explicit act
    return _SERVED_WRITES_AUTHORIZED


def set_served_writes_authorized(value: bool) -> None:
    global _SERVED_WRITES_AUTHORIZED
    _SERVED_WRITES_AUTHORIZED = bool(value)


@contextlib.contextmanager
def authorize_served_writes():
    previous = _SERVED_WRITES_AUTHORIZED
    set_served_writes_authorized(True)
    try:
        yield
    finally:
        set_served_writes_authorized(previous)


def guarded_write_or_refuse_served(path, text: str, output_root=None) -> Path:
    """Leaf writers whose callers do not (yet) all carry a root. With output_root: the full guarded write. Without: the destination must not lie in the served
    tree unless served writes were explicitly authorized. Production callers pass output_root."""
    if output_root is not None:
        return guarded_write_text(output_root, path, text)
    if _in_served_tree(path) and not served_writes_authorized():
        raise WriteBoundaryError(f"refused: {path} is inside the served company tree and no output_root / served authorization was given")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    return destination


def _in_served_tree(path) -> bool:
    try:
        resolved = Path(os.path.realpath(os.fspath(path)))
    except (TypeError, ValueError):
        return False
    served = served_companies_root()
    return resolved == served or served in resolved.parents


def _served_write_audit(event, args):
    if event == "open":
        path, mode, flags = args
        if isinstance(path, int):
            return
        writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (isinstance(flags, int) and flags & _WRITE_FLAGS)
        if writing and not served_writes_authorized() and _in_served_tree(path):
            raise WriteBoundaryError(f"refused: {path} is inside the served company tree and served writes are not authorized "
                                     "(pipeline --authorize-served-write or core.context_paths.authorize_served_writes())")
    elif event in _PATH_EVENTS and not served_writes_authorized():
        # only the paths this event CHANGES: a link's target, or a copy's source, is merely read
        written = args[1:2] if event in _DESTINATION_ONLY_EVENTS else args
        for arg in written:
            if isinstance(arg, (str, bytes, os.PathLike)) and _in_served_tree(arg):
                raise WriteBoundaryError(f"refused: {event} on {arg!r}, inside the served company tree, without served-write authorization")


if not getattr(sys, "_prometheus_served_write_guard", False):
    sys._prometheus_served_write_guard = True
    sys.addaudithook(_served_write_audit)


def configure_company_root(companies_root, *, authorize_served: bool = False, read_only: bool = False) -> Path:
    """For governance/certification scripts: validate the explicit company-data root they were given. Authorizing the served tree requires BOTH the served root
    and authorize_served=True (a CLI flag, never an environment variable); anything else fails closed."""
    root = resolve_output_root(companies_root, authorize_served=authorize_served or read_only)   # read_only: the served tree may be READ; the backstop still refuses writes
    if authorize_served and not read_only and _touches_served(root):
        set_served_writes_authorized(True)
    return root
