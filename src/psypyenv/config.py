from __future__ import annotations

import configparser
import os
from pathlib import Path
from typing import Iterable, List, Optional

from platformdirs import user_config_path


APP_NAME = "psypyenv"
CONFIG_SECTION = "conda"
CONFIG_KEY = "path"
CONFIG_EXTRA_PATHS_KEY = "extra_paths"


def _config_file() -> Path:
    directory = Path(user_config_path(APP_NAME, ensure_exists=True))
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "settings.ini"


def save_conda_path(conda_path: str) -> None:
    config = _load_or_create()
    config[CONFIG_SECTION][CONFIG_KEY] = conda_path
    _write_config(config)


def load_conda_path() -> Optional[str]:
    config = _read_config()
    if config is None or CONFIG_SECTION not in config:
        return None
    section = config[CONFIG_SECTION]
    return section.get(CONFIG_KEY)


def load_conda_search_paths() -> List[str]:
    config = _read_config()
    if config is None or CONFIG_SECTION not in config:
        return []
    section = config[CONFIG_SECTION]
    raw_value = section.get(CONFIG_EXTRA_PATHS_KEY, "")
    if not raw_value:
        return []
    return [item for item in (part.strip() for part in raw_value.split(os.pathsep)) if item]


def save_conda_search_paths(paths: Iterable[str]) -> None:
    normalized = []
    for path in paths:
        if not path:
            continue
        stripped = str(path).strip()
        if not stripped:
            continue
        normalized.append(stripped)
    config = _load_or_create()
    if normalized:
        config[CONFIG_SECTION][CONFIG_EXTRA_PATHS_KEY] = os.pathsep.join(normalized)
    elif CONFIG_EXTRA_PATHS_KEY in config[CONFIG_SECTION]:
        del config[CONFIG_SECTION][CONFIG_EXTRA_PATHS_KEY]
    _write_config(config)


def add_conda_search_path(path: str) -> None:
    current = load_conda_search_paths()
    normalized = str(path).strip()
    if not normalized or normalized in current:
        return
    current.append(normalized)
    save_conda_search_paths(current)


def _load_or_create() -> configparser.ConfigParser:
    config = _read_config()
    if config is None:
        config = configparser.ConfigParser()
    if CONFIG_SECTION not in config:
        config[CONFIG_SECTION] = {}
    return config


def _read_config() -> Optional[configparser.ConfigParser]:
    file_path = _config_file()
    if not file_path.exists():
        return None
    config = configparser.ConfigParser()
    config.read(file_path)
    return config


def _write_config(config: configparser.ConfigParser) -> None:
    file_path = _config_file()
    with file_path.open("w", encoding="utf-8") as handle:
        config.write(handle)
