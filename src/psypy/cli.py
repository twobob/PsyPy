from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

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
        conda_path = find_conda_executable(conda_candidate)
        if not conda_path:
            logging.warning("Conda executable not found.")
            return targets
        environments = list_conda_environments(conda_path)
        for env_path in environments:
            python_path = resolve_python_executable(env_path)
            if not python_path:
                logging.debug("Python executable not found for env %s", env_path)
                continue
            name = env_path.name or "base"
            add_target(name, python_path)

    return targets


if __name__ == "__main__":
    sys.exit(main())
