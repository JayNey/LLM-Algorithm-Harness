"""Shared experiment/A-B results root tests."""

from pathlib import Path

import pytest

from api.config import settings
from api.results import ensure_results_root, resolve_results_path, results_root

REPO = Path(__file__).resolve().parents[1]


def test_default_results_root_is_repo_local(monkeypatch):
    monkeypatch.setattr(settings, "RESULTS_ROOT", "results")

    assert results_root() == (REPO / "results").resolve()


def test_results_root_honors_absolute_override(monkeypatch, tmp_path):
    root = tmp_path / "shared-results"
    monkeypatch.setattr(settings, "RESULTS_ROOT", str(root))

    assert results_root() == root.resolve()


def test_results_root_resolves_relative_values_against_repo(monkeypatch):
    monkeypatch.setattr(settings, "RESULTS_ROOT", "custom-results")

    assert results_root() == (REPO / "custom-results").resolve()


def test_resolve_results_path_re_roots_legacy_relative_paths(monkeypatch, tmp_path):
    root = tmp_path / "shared-results"
    monkeypatch.setattr(settings, "RESULTS_ROOT", str(root))

    assert resolve_results_path("results/experiments/api/abc") == root / "experiments/api/abc"
    assert resolve_results_path("experiments/api/abc") == root / "experiments/api/abc"
    absolute = tmp_path / "elsewhere" / "artifact.json"
    assert resolve_results_path(str(absolute)) == absolute


def test_ensure_results_root_creates_configured_directory(monkeypatch, tmp_path):
    root = tmp_path / "nested" / "results"
    monkeypatch.setattr(settings, "RESULTS_ROOT", str(root))

    assert ensure_results_root() == root.resolve()
    assert root.is_dir()


def test_ensure_results_root_rejects_unwritable_location(monkeypatch, tmp_path):
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(settings, "RESULTS_ROOT", str(blocked))

    with pytest.raises(RuntimeError, match="RESULTS_ROOT is not writable") as excinfo:
        ensure_results_root()

    assert str(blocked.resolve()) in str(excinfo.value)
