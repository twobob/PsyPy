from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from packaging.requirements import InvalidRequirement, Requirement

from .models import PackageRequirement, RequirementSpec


LOGGER = logging.getLogger(__name__)


def parse_requirements(path: Path) -> Tuple[List[PackageRequirement], List[str]]:
    requirements: List[PackageRequirement] = []
    extra_indexes: List[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            parsed = parse_requirement_line(line)
        except InvalidRequirement as exc:
            LOGGER.warning("Invalid requirement at line %s: %s", line_number, exc)
            continue
        if parsed is None:
            continue
        package, extra = parsed
        if extra is not None:
            extra_indexes.append(extra)
            continue
        if package is not None:
            requirements.append(package)
    return requirements, extra_indexes


def parse_requirement_line(line: str) -> Optional[Tuple[Optional[PackageRequirement], Optional[str]]]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("--extra-index-url"):
        parts = stripped.split(None, 1)
        if len(parts) == 2:
            return (None, parts[1].strip())
        return (None, None)
    if stripped.startswith("--"):
        return None
    if any(prefix in stripped for prefix in ("http://", "https://", "git+")):
        if "#egg=" in stripped:
            egg_name = stripped.split("#egg=")[1].split("&")[0].strip()
            return (_build_requirement(egg_name, [], stripped, stripped), None)
        return None
    base = stripped.split("#", 1)[0].strip()
    if not base:
        return None
    return (_parse_standard_requirement(base, stripped), None)


def parse_requirement_text(text: Sequence[str]) -> List[PackageRequirement]:
    requirements: List[PackageRequirement] = []
    for line in text:
        parsed = parse_requirement_line(line)
        if parsed is None:
            continue
        package, _ = parsed
        if package is not None:
            requirements.append(package)
    return requirements


def parse_single_requirement(requirement: str) -> PackageRequirement:
    parsed = parse_requirement_line(requirement)
    if parsed is None or parsed[0] is None:
        raise InvalidRequirement(requirement)
    return parsed[0]


def _parse_standard_requirement(requirement: str, original: str) -> PackageRequirement:
    try:
        parsed = Requirement(requirement)
    except InvalidRequirement as exc:
        raise InvalidRequirement(requirement) from exc
    specs = [RequirementSpec(spec.operator, spec.version) for spec in parsed.specifier]
    marker = str(parsed.marker) if parsed.marker else None
    url = parsed.url
    return PackageRequirement(
        name=parsed.name.lower(),
        specs=specs,
        marker=marker,
        url=url,
        original=original,
    )


def _build_requirement(name: str, specs: Iterable[RequirementSpec], original: str, url: Optional[str]) -> PackageRequirement:
    return PackageRequirement(
        name=name.lower(),
        specs=list(specs),
        marker=None,
        url=url,
        original=original,
    )
