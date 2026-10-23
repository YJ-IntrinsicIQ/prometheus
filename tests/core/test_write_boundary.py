"""P0 write-safety: the shared output-boundary guard (core/context_paths.py). Disposable tmp trees only; never the served companies/ directory."""
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from core import context_paths as cp  # noqa: E402


def test_the_served_root_is_fixed_by_file_location_not_by_cwd(tmp_path, monkeypatch):
    before = cp.served_companies_root()
    monkeypatch.chdir(tmp_path)
    assert cp.served_companies_root() == before == (REPO / "companies").resolve()


@pytest.mark.parametrize("bad", [None, "", "companies", Path("companies"), "relative/root", Path(".")])
def test_a_missing_or_relative_root_is_rejected(bad):
    with pytest.raises(cp.WriteBoundaryError):
        cp.resolve_output_root(bad)


def test_a_scratch_root_is_accepted_and_resolved(tmp_path):
    assert cp.resolve_output_root(tmp_path / "scratch") == (tmp_path / "scratch").resolve()


def test_the_served_root_needs_explicit_authorization():
    served = cp.served_companies_root()
    with pytest.raises(cp.WriteBoundaryError):
        cp.resolve_output_root(served)
    with pytest.raises(cp.WriteBoundaryError):
        cp.resolve_output_root(served / "sun_pharma")
    with pytest.raises(cp.WriteBoundaryError):
        cp.resolve_output_root(REPO)                        # contains the served tree
    assert cp.resolve_output_root(served, authorize_served=True) == served


def test_a_symlink_to_the_served_root_is_still_the_served_root(tmp_path):
    link = tmp_path / "innocent"
    link.symlink_to(cp.served_companies_root())
    with pytest.raises(cp.WriteBoundaryError):
        cp.resolve_output_root(link)


def test_destinations_must_stay_inside_the_root(tmp_path):
    root = cp.resolve_output_root(tmp_path / "r")
    root.mkdir()
    assert cp.safe_destination(root, "a/b.json") == root / "a" / "b.json"
    for escape in ("../x.json", "a/../../x.json", str(tmp_path / "elsewhere.json"), "/etc/passwd"):
        with pytest.raises(cp.WriteBoundaryError):
            cp.safe_destination(root, escape)


def test_a_symlinked_directory_cannot_redirect_a_write_out_of_the_root(tmp_path):
    root = cp.resolve_output_root(tmp_path / "r")
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "sneaky").symlink_to(outside)
    with pytest.raises(cp.WriteBoundaryError):
        cp.safe_destination(root, "sneaky/file.json")
    assert list(outside.iterdir()) == []


def test_guarded_write_is_atomic_inside_the_root_and_respects_force(tmp_path):
    root = cp.resolve_output_root(tmp_path / "r")
    p = cp.guarded_write_text(root, "d/f.json", "one\n")
    assert p.read_text() == "one\n" and list(p.parent.glob("*.tmp")) == []
    cp.guarded_write_text(root, "d/f.json", "two\n", force=False)
    assert p.read_text() == "one\n"
    cp.guarded_write_text(root, "d/f.json", "two\n")
    assert p.read_text() == "two\n"


def test_guarded_write_refuses_an_escape_and_writes_nothing(tmp_path):
    root = cp.resolve_output_root(tmp_path / "r")
    with pytest.raises(cp.WriteBoundaryError):
        cp.guarded_write_text(root, "../leak.json", "x")
    assert not (tmp_path / "leak.json").exists()


def test_the_working_directory_cannot_redirect_a_write(tmp_path, monkeypatch):
    root = cp.resolve_output_root(tmp_path / "r")
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    p = cp.guarded_write_text(root, "f.json", "x")
    assert p == root / "f.json" and list(other.iterdir()) == []
