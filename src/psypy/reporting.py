from __future__ import annotations

import json
from dataclasses import asdict
from typing import Iterable, List, Optional, Sequence

from .models import EnvironmentReport


def format_reports(
    reports: Sequence[EnvironmentReport],
    recommended_python: Optional[str] = None,
    include_paths: bool = False,
) -> str:
    if not reports:
        return "No environments were inspected."
    sorted_reports = sorted(reports, key=lambda item: item.compatibility, reverse=True)
    lines: List[str] = []
    lines.append("=" * 72)
    lines.append("Environment compatibility summary")
    lines.append("=" * 72)
    if recommended_python:
        lines.append(f"Recommended Python version: {recommended_python}")
        lines.append("")
    for report in sorted_reports:
        lines.append(_format_single_report(report, include_paths))
    return "\n".join(line for line in lines if line is not None)


def _format_single_report(report: EnvironmentReport, include_paths: bool) -> str:
    name_line = report.name
    if report.python_version:
        name_line = f"{name_line} (Python {report.python_version})"
    if include_paths:
        name_line = f"{name_line} -> {report.python_executable}"
    lines = [name_line]
    lines.append(f"Compatibility: {report.compatibility:.1f}% of {report.total_requirements} applicable requirements")
    if report.matching:
        lines.append("Matches: " + ", ".join(sorted(report.matching)))
    if report.missing:
        lines.append("Missing: " + ", ".join(sorted(report.missing)))
    if report.mismatched:
        lines.append("Version conflicts: " + ", ".join(sorted(report.mismatched)))
    return "\n".join(lines)


def reports_to_json(reports: Iterable[EnvironmentReport]) -> str:
    payload = [asdict(report) for report in reports]
    return json.dumps(payload, indent=2, default=str)
