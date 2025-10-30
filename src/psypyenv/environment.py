from __future__ import annotations

import json
import logging
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from packaging.markers import Marker
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from .config import load_conda_path, load_conda_search_paths, save_conda_path
from .models import EnvironmentReport, PackageRequirement, RequirementSpec


LOGGER = logging.getLogger(__name__)


def normalize_name(name: str) -> str:
    return name.lower().replace("_", "-")


def get_installed_packages(python_executable: Path, timeout: int = 60) -> Dict[str, str]:
    try:
        result = subprocess.run(
            [str(python_executable), "-m", "pip", "list", "--format=json"],
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        LOGGER.debug("pip list failed for %s: %s", python_executable, exc)
    else:
        try:
            data = json.loads(result.stdout)
            return {normalize_name(pkg["name"]): pkg["version"] for pkg in data}
        except json.JSONDecodeError as exc:
            LOGGER.debug("pip list JSON parse failed for %s: %s", python_executable, exc)
    try:
        result = subprocess.run(
            [str(python_executable), "-m", "pip", "freeze"],
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        LOGGER.warning("pip freeze failed for %s: %s", python_executable, exc)
        return {}
    packages: Dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "==" not in line:
            continue
        name, version = line.split("==", 1)
        packages[normalize_name(name.strip())] = version.strip()
    return packages


def get_python_version(python_executable: Path) -> Optional[str]:
    try:
        result = subprocess.run(
            [str(python_executable), "--version"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        LOGGER.warning("Python version detection failed for %s: %s", python_executable, exc)
        return None
    output = f"{result.stdout.strip()} {result.stderr.strip()}".strip()
    match = re.search(r"Python\s*(\d+\.\d+(?:\.\d+)?)", output)
    return match.group(1) if match else None


def evaluate_marker(marker: Optional[str], python_version: Optional[str]) -> bool:
    if not marker:
        return True
    if python_version:
        base_version = ".".join(python_version.split(".")[:2])
    else:
        base_version = platform.python_version()
        python_version = platform.python_version()
    env = {
        "python_version": base_version,
        "python_full_version": python_version,
        "sys_platform": sys.platform,
        "platform_system": platform.system(),
        "platform_machine": platform.machine(),
    }
    try:
        return Marker(marker).evaluate(env)
    except Exception as exc:  # packaging does not expose a specific error
        LOGGER.warning("Failed to evaluate marker %s: %s", marker, exc)
        return True


def check_version(installed: str, specs: Sequence[RequirementSpec], package: str) -> bool:
    if not specs:
        return True
    try:
        installed_version = Version(installed)
    except InvalidVersion:
        LOGGER.warning("Invalid installed version %s for %s", installed, package)
        return False
    requirement_specs = list(specs)
    if normalize_name(package) == "python":
        adjusted: List[RequirementSpec] = []
        for spec in requirement_specs:
            if spec.operator == "==" and len(spec.version.split(".")) == 2:
                adjusted.append(RequirementSpec("~=", spec.version))
            else:
                adjusted.append(spec)
        requirement_specs = adjusted
    spec_expression = ",".join(f"{item.operator}{item.version}" for item in requirement_specs)
    try:
        spec_set = SpecifierSet(spec_expression)
    except InvalidSpecifier:
        LOGGER.warning("Invalid specifier %s for %s", spec_expression, package)
        return True
    return installed_version in spec_set


def inspect_environment(
    name: str,
    python_executable: Path,
    requirements: Sequence[PackageRequirement],
) -> EnvironmentReport:
    packages = get_installed_packages(python_executable)
    python_version = get_python_version(python_executable)
    matching: List[str] = []
    missing: List[str] = []
    mismatched: List[str] = []
    applicable = 0
    for requirement in requirements:
        if not evaluate_marker(requirement.marker, python_version):
            continue
        applicable += 1
        key = normalize_name(requirement.name)
        installed = packages.get(key)
        if installed is None:
            missing.append(requirement.name)
            continue
        if check_version(installed, requirement.specs, requirement.name):
            matching.append(requirement.name)
        else:
            mismatched.append(requirement.name)
    compatibility = (len(matching) / applicable * 100) if applicable else 100.0
    return EnvironmentReport(
        name=name,
        python_executable=python_executable,
        python_version=python_version,
        compatibility=compatibility,
        matching=matching,
        missing=missing,
        mismatched=mismatched,
        total_requirements=applicable,
    )


def find_conda_executable(candidate: Optional[str] = None) -> Optional[Path]:
    candidates: List[Path] = []
    if candidate:
        candidates.append(Path(candidate))
    saved = load_conda_path()
    if saved:
        candidates.append(Path(saved))
    for extra in load_conda_search_paths():
        extra_path = Path(extra)
        if extra_path.is_file():
            candidates.append(extra_path)
            continue
        if extra_path.is_dir():
            candidates.extend(_expand_conda_from_directory(extra_path))
        else:
            candidates.append(extra_path)
    env_var = os.environ.get("CONDA_EXE")
    if env_var:
        candidates.append(Path(env_var))
    for path_entry in os.environ.get("PATH", "").split(os.pathsep):
        if not path_entry:
            continue
        entry_path = Path(path_entry)
        names = ["conda"]
        if sys.platform == "win32":
            names = ["conda.exe", "conda.bat", "conda"]
        for name in names:
            candidate_path = entry_path / name
            if candidate_path.exists():
                candidates.append(candidate_path)
    default_candidates = _default_conda_locations()
    candidates.extend(default_candidates)
    seen: set[Path] = set()
    for path_candidate in candidates:
        normalized = path_candidate.resolve() if path_candidate.exists() else path_candidate
        if normalized in seen:
            continue
        seen.add(normalized)
        if _validate_conda(normalized):
            save_conda_path(str(normalized))
            return normalized
    return None


def _expand_conda_from_directory(directory: Path) -> List[Path]:
    names = ["conda"]
    if sys.platform == "win32":
        names = ["conda.exe", "conda.bat", "conda"]
        subdirectories = [Path(""), Path("Scripts"), Path("condabin")]
    else:
        subdirectories = [Path(""), Path("bin"), Path("condabin")]
    candidates: List[Path] = []
    for subdirectory in subdirectories:
        for name in names:
            candidate = directory / subdirectory / name
            candidates.append(candidate)
    return candidates


def _validate_conda(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        result = subprocess.run(
            [str(path), "--version"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False
    except OSError:
        if sys.platform == "win32":
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                return False
            return "conda" in content.lower()
        return False
    return "conda" in result.stdout.lower() or "conda" in result.stderr.lower()


def _default_conda_locations() -> Iterable[Path]:
    if sys.platform == "win32":
        prefixes = [
            Path("C:/ProgramData/Anaconda3"),
            Path("C:/ProgramData/miniconda3"),
            Path.home() / "Anaconda3",
            Path.home() / "miniconda3",
        ]
        for prefix in prefixes:
            yield prefix / "Scripts" / "conda.exe"
            yield prefix / "condabin" / "conda.bat"
        yield Path("C:/webui/installer_files/conda/condabin/conda.bat")
        yield Path("C:/webui/installer_files/conda/Scripts/conda.exe")
    else:
        prefixes = [
            Path.home() / "miniconda3" / "bin" / "conda",
            Path.home() / "anaconda3" / "bin" / "conda",
            Path("/opt/conda/bin/conda"),
            Path("/usr/local/anaconda3/bin/conda"),
            Path("/usr/local/miniconda3/bin/conda"),
        ]
        for prefix in prefixes:
            yield prefix


def list_conda_environments(conda_executable: Path) -> List[Path]:
    try:
        result = subprocess.run(
            [str(conda_executable), "env", "list", "--json"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        LOGGER.warning("conda env list failed for %s: %s", conda_executable, exc)
        return []
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        LOGGER.warning("conda env list JSON decode failed for %s: %s", conda_executable, exc)
        return []
    envs = payload.get("envs", [])
    return [Path(env).resolve() for env in envs if Path(env).exists()]


def resolve_python_executable(env_path: Path) -> Optional[Path]:
    candidates = [env_path / "python"]
    if sys.platform == "win32":
        candidates = [env_path / "python.exe", env_path / "Scripts" / "python.exe"]
    else:
        candidates.append(env_path / "bin" / "python")
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def infer_python_version(requirements: Sequence[PackageRequirement]) -> Optional[str]:
    python_specs: List[str] = []
    for requirement in requirements:
        if normalize_name(requirement.name) != "python":
            continue
        for spec in requirement.specs:
            python_specs.append(f"{spec.operator}{spec.version}")
    if not python_specs:
        return None
    try:
        spec_set = SpecifierSet(",".join(python_specs))
    except InvalidSpecifier:
        return None
    for version in ["3.12", "3.11", "3.10", "3.9", "3.8"]:
        if Version(version + ".0") in spec_set:
            return version
    return None
