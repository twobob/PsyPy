from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from psypyenv.requirements import parse_requirements


def _collect_samples(directory: Path) -> list[Path]:
    if not directory.exists():
        raise FileNotFoundError(f"Sample directory does not exist: {directory}")
    return sorted(path for path in directory.glob("*.txt") if path.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Parse sample requirements files and display a short summary.",
    )
    parser.add_argument(
        "--directory",
        type=Path,
        default=ROOT_DIR / "tests" / "data" / "requirements_samples",
        help="Directory containing sample requirements files.",
    )
    args = parser.parse_args()

    samples = _collect_samples(args.directory)
    if not samples:
        print("No requirements samples were found.")
        return 1

    for sample in samples:
        requirements, indexes = parse_requirements(sample)
        requirement_names = ", ".join(req.name for req in requirements) or "<none>"
        extra_indexes = ", ".join(indexes) or "<none>"
        print(f"== {sample.name} ==")
        print(f"Packages: {requirement_names}")
        print(f"Extra indexes: {extra_indexes}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
