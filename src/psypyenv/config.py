from __future__ import annotations

import configparser
from pathlib import Path
from typing import Optional

from platformdirs import user_config_path


APP_NAME = "psypyenv"
CONFIG_SECTION = "conda"
CONFIG_KEY = "path"


def _config_file() -> Path:
    directory = Path(user_config_path(APP_NAME, ensure_exists=True))
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "settings.ini"


def save_conda_path(conda_path: str) -> None:
    config = configparser.ConfigParser()
    file_path = _config_file()
    if file_path.exists():
        config.read(file_path)
    if CONFIG_SECTION not in config:
        config[CONFIG_SECTION] = {}
    config[CONFIG_SECTION][CONFIG_KEY] = conda_path
    with file_path.open("w", encoding="utf-8") as handle:
        config.write(handle)


def load_conda_path() -> Optional[str]:
    file_path = _config_file()
    if not file_path.exists():
        return None
    config = configparser.ConfigParser()
    config.read(file_path)
    if CONFIG_SECTION not in config:
        return None
    section = config[CONFIG_SECTION]
    return section.get(CONFIG_KEY)
