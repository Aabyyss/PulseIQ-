"""Compare the installed environment with `requirements.lock.txt`, or re-emit it.

`requirements.lock.txt` pins the toolchain the gate runs on, so moving it has to
be a deliberate act rather than a side effect. This script is the two operations
that move needs:

* `--check` names every distribution whose installed version differs from the
  pin — what the weekly drift job runs after installing from the floors.
* `--freeze` prints the exact `name==version` block for a deliberate move, sorted
  and ready to paste under the lock's header.

It reads the environment rather than resolving it, so it must run after an
install: `pip install -r requirements-dev.txt` for the released floors, or that
command with `-c requirements.lock.txt` to confirm the pin itself installs.

Two distributions are deliberately outside the lock, because a workflow installs
them by other means: `pip` (every job upgrades the installer first) and
`en-core-web-sm` (the spaCy model, pinned by URL). Both are ignored here so they
cannot create phantom drift or be pasted into the lock.

Exit status is 0 when the environment matches the lock and 1 when it does not, so
a workflow can fail on drift without parsing the output. Run it where the gate
runs — Python 3.12 on Linux — because the lock describes that image: a Windows
checkout has no `uvloop` and will name it as missing.
"""

from __future__ import annotations

import argparse
import os
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "requirements.lock.txt"

# Installed by the workflow itself, not by the lock: see the module docstring.
EXCLUDED = {"pip", "en-core-web-sm"}


def normalise(name: str) -> str:
    """PEP 503 name normalisation, so `MarkupSafe` and `markup_safe` are one."""
    return name.lower().replace("_", "-").replace(".", "-")


def read_lock(path: Path = LOCK) -> dict[str, str]:
    """The pinned versions, by normalised name. Comments and markers are ignored."""
    versions: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = line.split("#", 1)[0].strip()
        if not entry or "==" not in entry:
            continue
        name, _, version = entry.partition("==")
        versions[normalise(name)] = version.strip().split(";")[0].strip()
    return versions


def installed() -> dict[str, tuple[str, str]]:
    """What is in this environment: normalised name -> (name as shipped, version)."""
    found: dict[str, tuple[str, str]] = {}
    for distribution in metadata.distributions():
        name = distribution.metadata["Name"]
        if not name:
            continue
        key = normalise(name)
        if key in EXCLUDED:
            continue
        found[key] = (name, distribution.version)
    return found


def drift(locked: dict[str, str], current: dict[str, tuple[str, str]]) -> list[dict]:
    """One row per difference: bumped, added by the floors, or dropped."""
    rows: list[dict] = []
    for key in sorted(set(locked) | set(current)):
        want = locked.get(key)
        have = current[key][1] if key in current else None
        if want == have:
            continue
        rows.append(
            {
                "name": current[key][0] if key in current else key,
                # ASCII only: this table is printed into logs that are not
                # always UTF-8, and a mojibake dash makes a report unreadable.
                "locked": want or "-",
                "installed": have or "-",
                "kind": "changed" if want and have else "added" if have else "removed",
            }
        )
    return rows


def freeze_block(current: dict[str, tuple[str, str]] | None = None) -> str:
    """The lock's package lines, sorted case-insensitively, one per line."""
    current = installed() if current is None else current
    lines = [f"{name}=={version}" for name, version in current.values()]
    return "\n".join(sorted(lines, key=str.lower))


def render_drift(rows: list[dict]) -> str:
    if not rows:
        return "The installed toolchain matches requirements.lock.txt."
    width = max(len(row["name"]) for row in rows)
    body = "\n".join(
        f"| {row['name']:<{width}} | {row['locked']:<12} | {row['installed']:<12} | {row['kind']} |"
        for row in rows
    )
    return (
        f"{len(rows)} distribution(s) differ from the pin:\n\n"
        "| package | locked | installed | kind |\n"
        "|---|---|---|---|\n"
        + body
    )


def emit_summary(text: str) -> None:
    """Append to the job summary when running in Actions; harmless elsewhere."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("## Toolchain drift\n\n" + text + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if the environment differs")
    parser.add_argument("--freeze", action="store_true", help="print the block for a move")
    parser.add_argument("--lock", type=Path, default=LOCK, help="lock file to compare against")
    args = parser.parse_args(argv)

    if args.freeze:
        print(freeze_block())
        return 0

    if not args.check:
        parser.error("choose --check or --freeze")

    rows = drift(read_lock(args.lock), installed())
    report = render_drift(rows)
    print(report)
    emit_summary(report)
    if rows:
        print(
            "::warning::the floors resolve a different toolchain than "
            f"{args.lock.name}; docs/CI.md has the steps to move the pin"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
