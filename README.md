# PsyPy Environment Checker

PsyPy is a utility that inspects Python environments and reports how well they satisfy a given `requirements.txt` file. The tool is designed for packaging on PyPI and can be used as a library or as a command-line application.

## Installation

Once published, install the package from PyPI:

```bash
pip install psypy-env-checker
```

For local development use the source tree:

```bash
pip install -e .
```

## Command-line usage

The `psypy-env-check` command analyses one or more Python environments. It reads the supplied requirements file, checks each environment, and prints a compatibility summary. The current interpreter is always inspected; additional interpreters or conda environments are optional.

```bash
psypy-env-check --requirements path/to/requirements.txt --include-conda-envs
```

Key options:

* `--python /path/to/python`: inspect a specific interpreter; can be repeated.
* `--include-conda-envs`: auto-detect conda environments and include each one.
* `--conda /path/to/conda`: provide an explicit conda executable path when auto-discovery fails.
* `--json`: emit machine-readable JSON instead of formatted text.
* `--show-paths`: include interpreter locations in the output.

Example output:

```
========================================================================
Environment compatibility summary
========================================================================
Recommended Python version: 3.10
base (Python 3.10.13)
Compatibility: 95.0% of 40 applicable requirements
Matches: numpy, pandas, torch
Missing: datasets
```

## Library usage

The package exposes parsing and inspection helpers for integration in other tooling:

```python
import sys
from pathlib import Path

from psypy import inspect_environment, parse_requirements

requirements, _ = parse_requirements(Path("requirements.txt"))
report = inspect_environment("current", Path(sys.executable), requirements)
print(report.compatibility)
```

Use `psypy.reporting.format_reports` to render human-readable summaries or `psypy.reporting.reports_to_json` to produce JSON for automation.

## Configuration and state

When `--include-conda-envs` is used the tool caches the discovered conda executable location in a platform-appropriate configuration directory (managed by `platformdirs`). This avoids repeated prompts while keeping the package portable across operating systems.
