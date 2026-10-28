"""The importer's drift check, tested without touching the network.

`scripts/import_uci_heart.py --check` rebuilds the dataset from UCI and fails a
push when the committed CSV, its provenance record or its attribution notice no
longer match the source. That check is only useful if it can tell "same data"
from "one cell changed", so the comparison is tested directly here:

* identical rows produce no findings;
* a changed value is reported with its row and column name;
* a changed header or a different row count is reported;
* the conflict cases a diff could miss — a missing attribution notice, a
  provenance record that describes a different file.

The rebuild itself needs egress and is exercised by CI; these tests cover the
reasoning that decides pass/fail, which is where a bug would silently turn the
gate green.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "import_uci_heart", ROOT / "scripts" / "import_uci_heart.py"
)
importer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(importer)

COLUMNS = importer.COLUMNS


def row(**overrides):
    values = {
        "age": "63", "sex": "1", "cp": "1", "trestbps": "145", "chol": "233",
        "fbs": "1", "restecg": "2", "thalach": "150", "exang": "0",
        "oldpeak": "2.3", "slope": "3", "ca": "0", "thal": "6", "target": "0",
    }
    values.update(overrides)
    return [values[column] for column in COLUMNS]


def test_an_identical_rebuild_reports_nothing():
    committed = [COLUMNS, row(), row(age="67", target="1")]
    assert importer.compare_rows(committed, committed[1:]) == []


def test_a_changed_cell_is_named_by_row_and_column():
    committed = [COLUMNS, row()]
    rebuilt = [row(age="64")]
    problems = importer.compare_rows(committed, rebuilt)
    assert len(problems) == 1
    assert "row 1 (age)" in problems[0]
    assert "'64'" in problems[0] and "'63'" in problems[0]


def test_a_changed_header_is_reported_even_when_rows_match():
    renamed = list(COLUMNS)
    renamed[0] = "AGE"
    problems = importer.compare_rows([renamed, row()], [row()])
    assert any("header changed" in problem for problem in problems)


def test_a_changed_row_count_is_reported():
    problems = importer.compare_rows([COLUMNS, row()], [row(), row(age="50")])
    assert any("row count changed: 1 committed, 2 rebuilt" in problem for problem in problems)


def test_an_empty_or_missing_committed_file_fails_closed():
    assert importer.compare_rows([], [row()]) == ["committed dataset is missing or empty"]


def test_comparison_stops_after_the_limit_but_says_so():
    committed = [COLUMNS] + [row(age=str(age)) for age in range(30, 40)]
    rebuilt = [row(age=str(age)) for age in range(50, 60)]
    problems = importer.compare_rows(committed, rebuilt, limit=3)
    assert problems[-1].startswith("... further differences suppressed")
    assert len(problems) <= 4


def test_the_committed_dataset_is_well_formed():
    committed = importer.read_committed()
    assert committed[0] == COLUMNS
    body = committed[1:]
    assert len(body) == 297
    assert all(len(entry) == len(COLUMNS) for entry in body)
    assert {entry[-1] for entry in body} == {"0", "1"}
    assert sum(entry[-1] == "1" for entry in body) == 137
    # normalise() strips integral floats; a `.0` here means the importer's
    # formatting was bypassed by a hand edit.
    assert not any(value.endswith(".0") for entry in body for value in entry)


def test_attribution_notice_is_complete():
    assert importer.check_attribution() == []


def test_attribution_drift_is_detected(tmp_path):
    partial = tmp_path / "ATTRIBUTION.md"
    partial.write_text("Dataset from UCI. No licence stated.\n", encoding="utf-8")
    problems = importer.check_attribution(partial)
    assert any("CC BY 4.0" in problem for problem in problems)
    assert any("10.24432/C52P4X" in problem for problem in problems)
    assert any("creativecommons.org" in problem for problem in problems)


def test_provenance_record_matches_the_committed_rows():
    body = importer.read_committed()[1:]
    summary = {
        "rows": len(body),
        "unique_rows": len({tuple(entry[:13]) for entry in body}),
        "disease": sum(entry[-1] == "1" for entry in body),
        "healthy": sum(entry[-1] == "0" for entry in body),
        "dropped_incomplete_rows": 6,
    }
    assert importer.check_provenance(summary) == []


def test_provenance_drift_is_detected(tmp_path):
    recorded = json.loads(importer.PROVENANCE.read_text(encoding="utf-8"))
    recorded["rows"] = 1025
    drifted = tmp_path / "heart_source.json"
    drifted.write_text(json.dumps(recorded), encoding="utf-8")

    problems = importer.check_provenance(
        {
            "rows": 297,
            "unique_rows": 297,
            "disease": 137,
            "healthy": 160,
            "dropped_incomplete_rows": 6,
        },
        drifted,
    )
    assert any("provenance rows" in problem for problem in problems)


def test_a_cached_archive_is_used_without_touching_the_network(monkeypatch, tmp_path):
    cached = tmp_path / "uci-heart-disease.zip"
    cached.write_bytes(b"cached-archive-bytes")

    def fail(*args, **kwargs):
        raise AssertionError("the cache hit must not download")

    monkeypatch.setattr(importer, "fetch_archive", fail)
    assert importer.load_archive(cached) == b"cached-archive-bytes"


def test_a_cache_miss_downloads_once_and_stores_the_archive(monkeypatch, tmp_path):
    target = tmp_path / "cache" / "uci-heart-disease.zip"
    calls = []

    def fake_fetch(url=importer.ARCHIVE_URL):
        calls.append(url)
        return b"fresh-download"

    monkeypatch.setattr(importer, "fetch_archive", fake_fetch)
    assert importer.load_archive(target) == b"fresh-download"
    assert calls == [importer.ARCHIVE_URL]
    assert target.read_bytes() == b"fresh-download"

    # Second run: no download, and the same bytes come back.
    monkeypatch.setattr(
        importer, "fetch_archive", lambda *a, **k: pytest.fail("second run downloaded again")
    )
    assert importer.load_archive(target) == b"fresh-download"


def test_without_an_archive_path_every_run_downloads(monkeypatch):
    calls = []
    monkeypatch.setattr(importer, "fetch_archive", lambda *a, **k: calls.append(1) or b"zip")
    assert importer.load_archive(None) == b"zip"
    assert importer.load_archive(None) == b"zip"
    assert len(calls) == 2


def test_the_four_site_export_preserves_missing_values():
    committed = importer.read_committed(importer.SITES_OUTPUT)
    assert committed[0] == importer.SITE_COLUMNS
    body = committed[1:]
    assert len(body) == 920

    counts = {site: sum(1 for row in body if row[0] == site) for site in ("cleveland", "hungarian", "switzerland", "va")}
    assert counts == {"cleveland": 303, "hungarian": 294, "switzerland": 123, "va": 200}

    # '?' becomes an empty cell, but a value the source wrote is never rewritten:
    # Switzerland stores an unmeasured cholesterol as 0, so the export keeps the
    # 0 and `site_evaluation` is what treats it as missing.
    chol = importer.SITE_COLUMNS.index("chol")
    swiss = [row for row in body if row[0] == "switzerland"]
    assert all(row[chol] == "0" for row in swiss)

    ca = importer.SITE_COLUMNS.index("ca")
    hungarian = [row for row in body if row[0] == "hungarian"]
    assert sum(1 for row in hungarian if row[ca] == "") == 291
    assert all(len(row) == len(importer.SITE_COLUMNS) for row in body)


def test_sites_provenance_matches_the_export():
    recorded = json.loads(importer.SITES_PROVENANCE.read_text(encoding="utf-8"))
    body = importer.read_committed(importer.SITES_OUTPUT)[1:]

    assert recorded["licence"] == "CC BY 4.0"
    assert recorded["rows"] == len(body) == 920
    assert set(recorded["sites"]) == {"cleveland", "hungarian", "switzerland", "va"}

    for site, entry in recorded["sites"].items():
        rows = [row for row in body if row[0] == site]
        assert entry["rows"] == len(rows)
        for column in ("ca", "thal"):
            index = importer.SITE_COLUMNS.index(column)
            assert entry["missing"][column] == sum(1 for row in rows if row[index] == "")
        assert entry["disease"] == sum(1 for row in rows if row[-1] == "1")


def test_check_flag_dispatches_to_the_comparison(monkeypatch):
    calls = []
    monkeypatch.setattr(importer, "check", lambda path=None: calls.append(path) or 7)
    assert importer.main(["--check"]) == 7
    assert calls == [None]


def test_check_flag_passes_the_archive_path_through(monkeypatch, tmp_path):
    archive = tmp_path / "uci.zip"
    calls = []
    monkeypatch.setattr(importer, "check", lambda path=None: calls.append(path) or 0)
    assert importer.main(["--check", "--archive", str(archive)]) == 0
    assert calls == [archive]
