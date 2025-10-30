from __future__ import annotations

import logging
import sys
from pathlib import Path

from psypyenv import cli, config, environment
from psypyenv.models import EnvironmentReport


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


def test_cli_include_conda_envs_reports_and_caches(tmp_path, monkeypatch, capsys, caplog) -> None:
    requirements_path = tmp_path / "requirements.txt"
    requirements_path.write_text("requests==2.31.0\n")

    settings_path = tmp_path / "settings.ini"
    monkeypatch.setattr(config, "_config_file", lambda: settings_path)

    fake_conda = tmp_path / "conda"
    fake_conda.write_text("#!/bin/sh\n")
    fake_conda.chmod(0o755)
    monkeypatch.setattr(cli, "find_conda_executable", lambda candidate=None: fake_conda)

    env_root = tmp_path / "envs"
    env_root.mkdir()
    python_paths: dict[Path, Path] = {}
    environments = []
    for name in ("alpha", "beta"):
        env_dir = env_root / name
        env_dir.mkdir()
        python_path = env_dir / "python"
        python_path.write_text("#!/bin/sh\n")
        python_path.chmod(0o755)
        environments.append(env_dir)
        python_paths[env_dir] = python_path

    monkeypatch.setattr(cli, "list_conda_environments", lambda _conda: environments)
    monkeypatch.setattr(cli, "resolve_python_executable", lambda env: python_paths.get(env))

    def fake_inspect(name: str, path: Path, requirements):
        return EnvironmentReport(
            name=name,
            python_executable=path,
            python_version="3.10",
            compatibility=100.0,
            matching=[requirement.name for requirement in requirements],
            missing=[],
            mismatched=[],
            total_requirements=len(requirements),
        )

    monkeypatch.setattr(cli, "inspect_environment", fake_inspect)

    caplog.set_level(logging.INFO)
    exit_code = cli.main(
        [
            "--requirements",
            str(requirements_path),
            "--include-conda-envs",
            "--show-paths",
            "--log-level",
            "INFO",
        ]
    )
    assert exit_code == 0
    first_output = capsys.readouterr().out
    assert "Environment compatibility summary" in first_output
    assert "alpha" in first_output and "beta" in first_output

    cached_envs = config.load_cached_conda_envs()
    expected_alpha = ("alpha", str(python_paths[environments[0]].resolve()))
    expected_beta = ("beta", str(python_paths[environments[1]].resolve()))
    assert expected_alpha in cached_envs
    assert expected_beta in cached_envs

    assert any("Scanning conda environment 1/2" in message for message in caplog.messages)

    caplog.clear()
    exit_code = cli.main(
        [
            "--requirements",
            str(requirements_path),
            "--include-conda-envs",
            "--show-paths",
            "--log-level",
            "INFO",
        ]
    )
    assert exit_code == 0
    capsys.readouterr()
    assert any("Reusing 2 cached conda environments." in message for message in caplog.messages)
