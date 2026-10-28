"""Build `data/heart.csv` from the UCI Heart Disease (Cleveland) original.

Why this exists
---------------
The file this project trained on was the widely circulated Kaggle `heart.csv`:
1,025 rows that turned out to contain 723 exact duplicates, with the target
column inverted, and no licence metadata that could be verified. The dataset is
the UCI Cleveland cohort; the cleaner, licensable original is downloadable from
UCI under CC BY 4.0. This script fetches that original, checks it byte-for-byte
against a pinned SHA-256, converts it, and writes the file the trainer reads.

What it does to the data (all of it recorded in `data/ATTRIBUTION.md`)
---------------------------------------------------------------------
1. Reads `processed.cleveland.data` from the official archive.
2. Drops the 6 records with a missing value (`?` in `ca` ×4, `thal` ×2) rather
   than imputing the two strongest predictors — 297 rows remain.
3. Renames the 13 columns to the names the model and API already use.
4. Binarises the 0–4 angiographic severity `num` into `target` (1 = disease,
   0 = no disease) and asserts the direction from feature means, so an inverted
   file cannot be imported silently.

Re-run with::

    python scripts/import_uci_heart.py

Only the Python standard library is used, so this works offline after the
download and adds no dependency. The archive and the member file are both
checksum-pinned; a mismatch stops the import instead of training on a payload
nobody reviewed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "heart.csv"
PROVENANCE = ROOT / "data" / "heart_source.json"

ARCHIVE_URL = "https://archive.ics.uci.edu/static/public/45/heart+disease.zip"
MEMBER = "processed.cleveland.data"

# SHA-256 of the archive and member verified on 2026-10-28. The member hash is
# what matters: the archive has been rebuilt by UCI before, the data has not.
ARCHIVE_SHA256 = "b17cd273da9ce1caa4710fce80227ea454d4dbf9fcbc8e6a9121672751563adc"
MEMBER_SHA256 = "a74b7efa387bc9d108d7d0115d831fe9b414b29ae7124f331b622b4efa0427c8"

COLUMNS = [
    "age",
    "sex",
    "cp",
    "trestbps",
    "chol",
    "fbs",
    "restecg",
    "thalach",
    "exang",
    "oldpeak",
    "slope",
    "ca",
    "thal",
    "target",
]

SOURCE = {
    "name": "UCI Heart Disease (Cleveland processed)",
    "repository": "UCI Machine Learning Repository, dataset 45",
    "url": "https://archive.ics.uci.edu/dataset/45/heart+disease",
    "download": ARCHIVE_URL,
    "doi": "10.24432/C52P4X",
    "licence": "CC BY 4.0",
    "licence_url": "https://creativecommons.org/licenses/by/4.0/",
    "citation": (
        "Janosi, A., Steinbrunn, W., Pfisterer, M., Detrano, R. (1988). "
        "Heart Disease. UCI Machine Learning Repository. https://doi.org/10.24432/C52P4X"
    ),
    "patients_attribution": (
        "Cleveland Clinic Foundation; data collected by Robert Detrano, M.D., Ph.D."
    ),
}


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def fetch_archive(url: str = ARCHIVE_URL) -> bytes:
    print(f"Downloading {url}")
    with urllib.request.urlopen(url, timeout=90) as response:  # noqa: S310 - pinned https URL
        payload = response.read()
    digest = _sha256(payload)
    if digest != ARCHIVE_SHA256:
        print(f"  WARNING: archive hash changed ({digest}); verifying the member file instead")
    return payload


def extract_member(archive: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        payload = bundle.read(MEMBER)
    digest = _sha256(payload)
    if digest != MEMBER_SHA256:
        raise SystemExit(
            f"{MEMBER} does not match the pinned SHA-256.\n"
            f"  expected {MEMBER_SHA256}\n  got      {digest}\n"
            "Refusing to build a dataset from an unreviewed payload."
        )
    return payload


def normalise(value: str) -> str:
    """`63.0` -> `63`, `2.3` -> `2.3`: integers where the source means integers."""
    try:
        number = float(value)
    except ValueError:
        return value
    if number.is_integer():
        return str(int(number))
    return value


def convert(payload: bytes) -> tuple[list[list[str]], dict]:
    text = payload.decode("utf-8")
    records = list(csv.reader(io.StringIO(text)))
    incomplete = [row for row in records if "?" in row]
    complete = [row for row in records if "?" not in row]
    assert all(len(row) == 14 for row in complete), "unexpected Cleveland column count"

    rows = []
    for row in complete:
        values = [normalise(value) for value in row[:13]]
        severity = int(float(row[13]))
        target = 1 if severity > 0 else 0
        rows.append(values + [str(target)])

    summary = summarise(records, incomplete, rows)
    return rows, summary


def summarise(records: list[list[str]], incomplete: list[list[str]], rows: list[list[str]]) -> dict:
    disease = [row for row in rows if row[13] == "1"]
    healthy = [row for row in rows if row[13] == "0"]

    def mean(group: list[list[str]], index: int) -> float:
        return sum(float(row[index]) for row in group) / len(group)

    # Direction check on the data itself: an inverted label would flip every
    # one of these. Kept here *and* in train_model.py, because the importer is
    # where a bad download would first appear.
    checks = {
        "thalach": (mean(disease, 7), mean(healthy, 7)),
        "oldpeak": (mean(disease, 9), mean(healthy, 9)),
        "ca": (mean(disease, 11), mean(healthy, 11)),
    }
    if not (checks["thalach"][0] < checks["thalach"][1]):
        raise SystemExit("label direction wrong: disease group has the higher max heart rate")
    if not (checks["oldpeak"][0] > checks["oldpeak"][1]):
        raise SystemExit("label direction wrong: disease group has the lower ST depression")
    if not (checks["ca"][0] > checks["ca"][1]):
        raise SystemExit("label direction wrong: disease group has fewer major vessels")

    feature_rows = {tuple(row[:13]) for row in rows}
    if len(feature_rows) != len(rows):
        raise SystemExit("duplicate feature vectors after conversion — refusing to write")

    return {
        "source_rows": len(records),
        "dropped_incomplete_rows": len(incomplete),
        "rows": len(rows),
        "disease": len(disease),
        "healthy": len(healthy),
        "unique_rows": len(feature_rows),
        "means": {name: {"disease": round(dis, 2), "healthy": round(hea, 2)} for name, (dis, hea) in checks.items()},
    }


def write_dataset(rows: list[list[str]]) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", newline="", encoding="utf-8") as handle:
        handle.write(serialise(rows))


def serialise(rows: list[list[str]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(COLUMNS)
    writer.writerows(rows)
    return buffer.getvalue()


def read_committed(path: Path = OUTPUT) -> list[list[str]]:
    """The CSV as checked in, parsed so line endings cannot masquerade as drift."""
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.reader(handle))


def compare_rows(
    committed: list[list[str]], rebuilt: list[list[str]], limit: int = 5
) -> list[str]:
    """Every difference between the committed file and a fresh build, named."""
    problems: list[str] = []
    if not committed:
        return ["committed dataset is missing or empty"]
    if committed[0] != COLUMNS:
        problems.append(f"header changed: {committed[0]} != {COLUMNS}")

    body = committed[1:]
    if len(body) != len(rebuilt):
        problems.append(f"row count changed: {len(body)} committed, {len(rebuilt)} rebuilt")

    for index, (old, new) in enumerate(zip(body, rebuilt)):
        if old == new:
            continue
        if len(old) != len(new):
            problems.append(f"row {index + 1}: {len(old)} columns committed, {len(new)} rebuilt")
            continue
        for column, (before, after) in enumerate(zip(old, new)):
            if before != after:
                name = COLUMNS[column] if column < len(COLUMNS) else f"column {column}"
                problems.append(
                    f"row {index + 1} ({name}): committed {before!r}, rebuilt {after!r}"
                )
        if len(problems) >= limit:
            problems.append("... further differences suppressed")
            break
    return problems


ATTRIBUTION_PATH = ROOT / "data" / "ATTRIBUTION.md"


def check_attribution(path: Path = ATTRIBUTION_PATH) -> list[str]:
    """CC BY 4.0 requires attribution; the notice is part of the dataset."""
    if not path.exists():
        return [f"attribution file missing: {path.relative_to(ROOT)}"]
    text = path.read_text(encoding="utf-8")
    required = [
        "CC BY 4.0",
        "creativecommons.org/licenses/by/4.0",
        SOURCE["doi"],
        "UCI",
        "Detrano",
    ]
    return [f"attribution does not mention {value!r}" for value in required if value not in text]


def check_provenance(summary: dict, path: Path = PROVENANCE) -> list[str]:
    """The shipped provenance record must describe the file being compared."""
    if not path.exists():
        return [f"provenance file missing: {path.relative_to(ROOT)}"]
    recorded = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "licence": SOURCE["licence"],
        "member_sha256": MEMBER_SHA256,
        "columns": COLUMNS,
        "rows": summary["rows"],
        "unique_rows": summary["unique_rows"],
        "disease": summary["disease"],
        "healthy": summary["healthy"],
        "dropped_incomplete_rows": summary["dropped_incomplete_rows"],
    }
    problems = []
    for key, value in expected.items():
        if recorded.get(key) != value:
            problems.append(f"provenance {key}: recorded {recorded.get(key)!r}, expected {value!r}")
    return problems


def check() -> int:
    """Rebuild in memory and compare with what is committed. Writes nothing."""
    archive = fetch_archive()
    rows, summary = convert(extract_member(archive))
    problems = (
        compare_rows(read_committed(), rows)
        + check_attribution()
        + check_provenance(summary)
    )
    if problems:
        print("Dataset provenance check FAILED")
        for problem in problems:
            print(f"  - {problem}")
        print("Rebuild and commit the dataset (python scripts/import_uci_heart.py) if the change is intended.")
        return 1
    print(
        f"Dataset matches the importer: {summary['rows']} rows, "
        f"{summary['disease']} disease / {summary['healthy']} healthy, "
        f"licence {SOURCE['licence']}, attribution present"
    )
    return 0


def write_provenance(summary: dict) -> None:
    provenance = {
        **SOURCE,
        "retrieved": date.today().isoformat(),
        "archive_sha256": ARCHIVE_SHA256,
        "member": MEMBER,
        "member_sha256": MEMBER_SHA256,
        "output": "data/heart.csv",
        "columns": COLUMNS,
        "transformations": [
            f"dropped {summary['dropped_incomplete_rows']} records with a missing value "
            "(ca x4, thal x2) instead of imputing them",
            "renamed the 13 predictor columns to the names the model uses",
            "binarised num (0-4 angiographic severity): target = 1 if num > 0 else 0",
            "exact duplicate feature vectors: none in this export",
        ],
        "target_encoding": "1 = disease, 0 = no disease (num > 0), verified from feature means",
        **{key: value for key, value in summary.items() if key != "means"},
        "direction_check": summary["means"],
    }
    PROVENANCE.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="rebuild in memory and compare with data/heart.csv, its provenance and its "
        "attribution; write nothing and exit non-zero on drift",
    )
    args = parser.parse_args(argv)

    if args.check:
        return check()

    archive = fetch_archive()
    payload = extract_member(archive)
    rows, summary = convert(payload)
    write_dataset(rows)
    write_provenance(summary)

    print(f"Wrote {OUTPUT.relative_to(ROOT)}: {summary['rows']} rows")
    print(
        f"  {summary['disease']} disease / {summary['healthy']} healthy · "
        f"{summary['unique_rows']} distinct · {summary['dropped_incomplete_rows']} incomplete dropped"
    )
    print(f"Wrote {PROVENANCE.relative_to(ROOT)} (CC BY 4.0 attribution + hashes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
