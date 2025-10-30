from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from .config import load_cached_conda_envs, save_cached_conda_envs
from .environment import (
    find_conda_executable,
    infer_python_version,
    inspect_environment,
    list_conda_environments,
    resolve_python_executable,
)
from .reporting import format_reports, reports_to_json
from .requirements import parse_requirements


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect Python environments and verify requirement compatibility.",
    )
    parser.add_argument(
        "-r",
        "--requirements",
        type=Path,
        default=Path("requirements.txt"),
        help="Path to the requirements file.",
    )
    parser.add_argument(
        "--python",
        dest="python_executables",
        action="append",
        help="Explicit Python interpreter to inspect. Can be provided multiple times.",
    )
    parser.add_argument(
        "--include-conda-envs",
        action="store_true",
        help="Inspect every conda environment discovered on the system.",
    )
    parser.add_argument(
        "--conda",
        type=str,
        help="Path to the conda executable if auto-detection fails.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit results as JSON instead of formatted text.",
    )
    parser.add_argument(
        "--show-paths",
        action="store_true",
        help="Display absolute interpreter paths in the text output.",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        help="Set the logging level (DEBUG, INFO, WARNING, ERROR).",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.log_level)

    requirements_path = args.requirements
    if not requirements_path.exists():
        parser.error(f"Requirements file not found: {requirements_path}")

    requirements, extra_indexes = parse_requirements(requirements_path)
    if not requirements:
        parser.error("No valid requirements were found.")

    recommended_python = infer_python_version(requirements)

    targets = _collect_targets(
        include_conda=args.include_conda_envs,
        conda_candidate=args.conda,
        explicit_pythons=args.python_executables,
    )

    if not targets:
        parser.error("No Python environments to inspect.")

    reports = [
        inspect_environment(name, path, requirements)
        for name, path in targets
    ]

    if args.json:
        print(reports_to_json(reports))
    else:
        text = format_reports(reports, recommended_python, include_paths=args.show_paths)
        if extra_indexes:
            text += "\n\nExtra package indexes:\n" + "\n".join(extra_indexes)
        print(text)

    return 0


def _configure_logging(level: str) -> None:
    numeric_level = getattr(logging, level.upper(), logging.WARNING)
    logging.basicConfig(level=numeric_level, format="%(levelname)s: %(message)s")


def _collect_targets(
    include_conda: bool,
    conda_candidate: Optional[str],
    explicit_pythons: Optional[Sequence[str]],
) -> List[Tuple[str, Path]]:
    targets: List[Tuple[str, Path]] = []
    seen: set[Path] = set()

    def add_target(name: str, path: Path) -> None:
        resolved = path.resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        targets.append((name, resolved))

    add_target("current", Path(sys.executable))

    if explicit_pythons:
        for index, item in enumerate(explicit_pythons, start=1):
            candidate = Path(item)
            if not candidate.exists():
                logging.warning("Python interpreter not found: %s", candidate)
                continue
            add_target(f"python-{index}", candidate)

    if include_conda:
        cached_entries = load_cached_conda_envs()
        cached_records: List[Tuple[str, str]] = []
        seen_cached_paths: set[Path] = set()

        def record_cache(env_name: str, python_path: Path) -> None:
            try:
                resolved_python = python_path.resolve()
            except FileNotFoundError:
                return
            if resolved_python in seen_cached_paths:
                return
            seen_cached_paths.add(resolved_python)
            cached_records.append((env_name, str(resolved_python)))

        if cached_entries:
            logging.info(
                "Reusing %s cached conda environment%s.",
                len(cached_entries),
                "" if len(cached_entries) == 1 else "s",
            )
        for index, (cached_name, cached_path) in enumerate(cached_entries, start=1):
            python_path = Path(cached_path)
            if not python_path.exists():
                continue
            logging.info(
                "Cached conda environment %s/%s: %s",
                index,
                len(cached_entries),
                python_path,
            )
            add_target(cached_name, python_path)
            record_cache(cached_name, python_path)

        conda_path = find_conda_executable(conda_candidate)
        if not conda_path:
            logging.warning("Conda executable not found.")
            save_cached_conda_envs(cached_records)
            return targets
        environments = list_conda_environments(conda_path)
        total_envs = len(environments)
        if total_envs:
            logging.info(
                "Scanning %s conda environment%s for Python interpreters...",
                total_envs,
                "" if total_envs == 1 else "s",
            )
        for index, env_path in enumerate(environments, start=1):
            python_path = resolve_python_executable(env_path)
            if not python_path:
                logging.debug("Python executable not found for env %s", env_path)
                continue
            logging.info(
                "Scanning conda environment %s/%s: %s",
                index,
                total_envs or 1,
                env_path,
            )
            name = env_path.name or "base"
            add_target(name, python_path)
            record_cache(name, python_path)
        save_cached_conda_envs(cached_records)

    return targets


if __name__ == "__main__":
    sys.exit(main())
