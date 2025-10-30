from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pytest

from psypyenv import cli


@pytest.fixture(scope="session")
def discovered_environments() -> List[Tuple[str, Path]]:
    return cli._collect_targets(
        include_conda=True,
        conda_candidate=None,
        explicit_pythons=None,
        refresh_cache=True,
    )


@pytest.fixture(scope="session", autouse=True)
def _ensure_environment_locator_runs(discovered_environments):
    # The autouse fixture guarantees that the environment locator executes
    # before any tests access the interpreter details.
    return discovered_environments
