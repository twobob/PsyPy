from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass(frozen=True)
class RequirementSpec:
    operator: str
    version: str


@dataclass(frozen=True)
class PackageRequirement:
    name: str
    specs: List[RequirementSpec] = field(default_factory=list)
    marker: Optional[str] = None
    url: Optional[str] = None
    original: Optional[str] = None


@dataclass(frozen=True)
class PackageStatus:
    name: str
    required: PackageRequirement
    installed_version: Optional[str]
    is_missing: bool
    is_mismatched: bool


@dataclass(frozen=True)
class EnvironmentReport:
    name: str
    python_executable: Path
    python_version: Optional[str]
    compatibility: float
    matching: List[str]
    missing: List[str]
    mismatched: List[str]
    total_requirements: int
