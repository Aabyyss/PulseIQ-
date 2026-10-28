"""Every package the gate imports has to be a package a fresh checkout installs.

The hosted backend job failed in eleven seconds on 2026-10-28, at collection,
naming no test. The cause was one import: `backend/test_ci_workflow.py` parses
`.github/workflows/tests.yml`, so it imports `yaml`, which was installed by hand
in a developer venv and by nothing in `requirements.txt` or
`requirements-dev.txt`. The suite was green on the laptop that had it and red on
the runner that did not.

A missing import fails before any test asserts anything, so it is the one kind of
breakage a green local run cannot be trusted for. This module checks the
declaration directly instead: walk the code the gate imports, resolve each
third-party module to the distribution that ships it, and require a line in one of
the requirements files. The second test proves the check can actually see a
missing package, so a refactor that makes it always pass fails here too.

Notebooks are out of scope: `matplotlib` lives there, and nothing in the gate
imports it.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = (ROOT / "requirements.txt", ROOT / "requirements-dev.txt")
LOCK = ROOT / "requirements.lock.txt"
SCANNED = ("backend", "agents", "scripts")

# Import name -> distribution name, where they differ. Anything absent is assumed
# to ship under its import name (`pandas`, `shap`, `spacy`, ...).
DISTRIBUTIONS = {
    "yaml": "pyyaml",
    "sklearn": "scikit-learn",
    "pil": "pillow",
    "imageio_ffmpeg": "imageio-ffmpeg",
}

REQUIREMENT_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


def normalise(name: str) -> str:
    return name.lower().replace("_", "-")


def declared_packages(paths: tuple[Path, ...] = REQUIREMENTS) -> set[str]:
    """The distributions a `pip install -r` would provide, by normalised name."""
    names: set[str] = set()
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            match = REQUIREMENT_NAME.match(line)
            if match:
                names.add(normalise(match.group(1)))
    return names


def local_modules(root: Path = ROOT) -> set[str]:
    """Top-level names in this repository, which pip is not expected to install.

    The scripts put their own directory on `sys.path` (`backend/test_full_pipeline.py`
    imports `orchestrator`), so a module sitting beside them is local too.
    """
    directories = [root, *(root / name for name in SCANNED)]
    names: set[str] = set()
    for directory in directories:
        if not directory.is_dir():
            continue
        names.update(
            entry.stem if entry.is_file() else entry.name for entry in directory.iterdir()
        )
    return names


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module.split(".")[0])
    return modules


def undeclared_packages(root: Path, requirements: tuple[Path, ...]) -> list[str]:
    """One line per import that no requirements file would install."""
    declared = declared_packages(requirements)
    local = local_modules(root)
    problems: list[str] = []
    seen: set[tuple[str, str]] = set()

    for directory in SCANNED:
        for path in sorted((root / directory).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            for module in sorted(imported_modules(path)):
                if module in sys.stdlib_module_names or module in local:
                    continue
                distribution = normalise(DISTRIBUTIONS.get(module, module))
                if distribution in declared or (distribution, module) in seen:
                    continue
                seen.add((distribution, module))
                problems.append(
                    f"{path.relative_to(root)} imports {module!r} "
                    f"(distribution {distribution!r}), which no requirements file declares"
                )
    return problems


def locked_versions(path: Path = LOCK) -> dict[str, str]:
    """The exact version each distribution is pinned to, by normalised name."""
    versions: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name, _, version = line.partition("==")
        versions[normalise(name)] = version.strip()
    return versions


def test_the_lock_pins_every_line_exactly() -> None:
    """A floor or a range would be the thing the lock exists to remove."""
    loose = []
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        entry = line.split("#", 1)[0].strip()
        if entry and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*==[^=<>!,\s]+", entry):
            loose.append(entry)
    assert not loose, "requirements.lock.txt must use `name==version`: " + ", ".join(loose)


def test_every_declared_dependency_is_pinned_in_the_lock() -> None:
    """A new direct dependency without a lock entry would float on the runner."""
    locked = locked_versions()
    missing = sorted(declared_packages() - set(locked))
    assert not missing, (
        "these direct requirements have no exact pin in requirements.lock.txt: "
        + ", ".join(missing)
    )


def test_the_lock_does_not_pin_the_same_package_twice() -> None:
    names = [
        normalise(line.split("#", 1)[0].split("==")[0])
        for line in LOCK.read_text(encoding="utf-8").splitlines()
        if "==" in line
    ]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    assert not duplicates, f"pinned twice: {duplicates}"


def test_every_third_party_import_is_declared() -> None:
    problems = undeclared_packages(ROOT, REQUIREMENTS)
    assert not problems, (
        "the gate imports packages a fresh checkout would not install, so CI fails "
        "before a single test names itself:\n  "
        + "\n  ".join(problems)
        + "\nAdd them to requirements.txt (runtime) or requirements-dev.txt (tests and tooling)."
    )


def test_the_check_reports_an_undeclared_import(tmp_path: Path) -> None:
    """Guard the guard: the 2026-10-28 failure must be reproducible by this test."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "probe.py").write_text("import yaml\n", encoding="utf-8")
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("pytest>=8.3\n", encoding="utf-8")

    problems = undeclared_packages(tmp_path, (requirements,))
    assert len(problems) == 1
    assert "yaml" in problems[0] and "pyyaml" in problems[0]

    requirements.write_text("pytest>=8.3\nPyYAML>=6.0\n", encoding="utf-8")
    assert undeclared_packages(tmp_path, (requirements,)) == []


def test_stdlib_and_local_imports_are_not_reported(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "probe.py").write_text(
        "import json\nimport orchestrator\nfrom agents import pharmacology_agent\n",
        encoding="utf-8",
    )
    (tmp_path / "orchestrator.py").write_text("", encoding="utf-8")
    (tmp_path / "agents").mkdir()
    (tmp_path / "requirements.txt").write_text("pytest>=8.3\n", encoding="utf-8")

    assert undeclared_packages(tmp_path, (tmp_path / "requirements.txt",)) == []
