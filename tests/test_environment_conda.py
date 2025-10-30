from __future__ import annotations

import sys
from pathlib import Path

from psypyenv import environment


def test_find_conda_executable_returns_none_when_absent(monkeypatch) -> None:
    monkeypatch.setattr(environment, "load_conda_path", lambda: None)
    monkeypatch.setattr(environment, "save_conda_path", lambda path: None)
    monkeypatch.setattr(environment, "load_conda_search_paths", lambda: [])
    monkeypatch.setattr(environment, "_default_conda_locations", lambda: [])
    monkeypatch.delenv("CONDA_EXE", raising=False)
    monkeypatch.setenv("PATH", "")

    result = environment.find_conda_executable()

    assert result is None


def test_find_conda_executable_uses_custom_paths(tmp_path, monkeypatch) -> None:
    custom_dir = tmp_path / "custom"
    custom_dir.mkdir()
    executable_name = "conda.exe" if sys.platform == "win32" else "conda"
    candidate = custom_dir / executable_name
    candidate.write_text("#!/bin/sh\necho 'conda 24.1'\n")
    candidate.chmod(0o755)

    saves: list[str] = []

    monkeypatch.setattr(environment, "load_conda_path", lambda: None)
    monkeypatch.setattr(environment, "save_conda_path", lambda path: saves.append(path))
    monkeypatch.setattr(environment, "load_conda_search_paths", lambda: [str(custom_dir)])
    monkeypatch.setattr(environment, "_default_conda_locations", lambda: [])
    monkeypatch.delenv("CONDA_EXE", raising=False)
    monkeypatch.setenv("PATH", "")

    resolved = environment.find_conda_executable()

    assert resolved == candidate.resolve()
    assert saves and Path(saves[0]) == resolved
