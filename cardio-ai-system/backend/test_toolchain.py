"""The drift checker itself: what counts as a difference, and what does not.

The weekly drift job is only useful if it can tell "the floors moved" from "the
same toolchain, written differently". These tests pin that reasoning without
touching the network or the real environment: a bumped version, a package the
floors added, one they dropped, a name that differs only in case or underscores,
and the two distributions the workflow installs by other means (`pip` and the
spaCy model) which must never be reported or emitted.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("toolchain", ROOT / "scripts" / "toolchain.py")
toolchain = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(toolchain)


def write_lock(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "requirements.lock.txt"
    path.write_text(body, encoding="utf-8")
    return path


def test_lock_parsing_ignores_comments_blanks_and_normalises_names(tmp_path):
    path = write_lock(
        tmp_path,
        "# a comment\n\nMarkup-Safe==3.0.4\nfoo_bar==2.0\nbaz==1.0 ; python_version > '3'\n",
    )
    assert toolchain.read_lock(path) == {
        "markup-safe": "3.0.4",
        "foo-bar": "2.0",
        "baz": "1.0",
    }


def test_identical_toolchains_report_no_drift():
    locked = {"pandas": "3.1.0", "numpy": "2.5.4"}
    current = {"pandas": ("pandas", "3.1.0"), "numpy": ("numpy", "2.5.4")}
    assert toolchain.drift(locked, current) == []
    assert "matches" in toolchain.render_drift([])


def test_a_bumped_added_and_dropped_package_are_each_named():
    locked = {"pandas": "3.0.5", "numpy": "2.5.3", "scipy": "1.18.1"}
    current = {"pandas": ("pandas", "3.1.0"), "numpy": ("numpy", "2.5.3"), "numba": ("numba", "0.67.0")}

    rows = {row["name"]: row for row in toolchain.drift(locked, current)}
    assert rows["pandas"]["kind"] == "changed"
    assert rows["pandas"]["locked"] == "3.0.5" and rows["pandas"]["installed"] == "3.1.0"
    assert rows["numba"]["kind"] == "added" and rows["numba"]["locked"] == "-"
    assert rows["scipy"]["kind"] == "removed" and rows["scipy"]["installed"] == "-"
    assert "numpy" not in rows, "an unchanged package must not appear at all"


def test_the_freeze_block_is_sorted_case_insensitively_and_exact():
    current = {
        "websockets": ("websockets", "17.3"),
        "MarkupSafe": ("MarkupSafe", "3.0.4"),
        "anyio": ("anyio", "4.15.1"),
    }
    assert toolchain.freeze_block(current) == (
        "anyio==4.15.1\nMarkupSafe==3.0.4\nwebsockets==17.3"
    )


def test_the_workflow_installed_packages_are_never_pinned_or_reported():
    """`pip` and the spaCy model are installed by URL/upgrade, not by the lock."""
    assert toolchain.EXCLUDED == {"pip", "en-core-web-sm"}
    real = toolchain.installed()
    assert "pip" not in real
    assert "en-core-web-sm" not in real
    assert toolchain.freeze_block(real).lower().find("pip==") == -1


def test_check_exits_nonzero_on_drift_and_zero_when_pinned(tmp_path, monkeypatch, capsys):
    path = write_lock(tmp_path, "pandas==3.1.0\n")
    monkeypatch.setattr(
        toolchain, "installed", lambda: {"pandas": ("pandas", "3.1.0")}
    )
    assert toolchain.main(["--check", "--lock", str(path)]) == 0

    monkeypatch.setattr(
        toolchain, "installed", lambda: {"pandas": ("pandas", "3.2.0")}
    )
    assert toolchain.main(["--check", "--lock", str(path)]) == 1
    output = capsys.readouterr().out
    assert "3.2.0" in output and "3.1.0" in output and "changed" in output
