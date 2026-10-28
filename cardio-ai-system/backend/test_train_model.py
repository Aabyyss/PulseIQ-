"""Guards on the screening model's evidence: provenance, split, polarity, card.

The model card once reported ROC-AUC 1.000 and recall 1.000 on a Kaggle copy of
the Cleveland data. Two defects produced that: 723 of its 1,025 rows were exact
duplicates split across train and test, and its target was inverted. The data is
now the UCI original (CC BY 4.0), imported by `scripts/import_uci_heart.py` from
a checksum-pinned download. These tests pin the properties that make that claim
true, so the flattering number cannot return by accident:

* the file is the 297-row complete Cleveland export, with no duplicate vectors;
* the split shares no patient profile between train and test;
* labels point the direction cardiology says they should (a reversed file fails);
* the metadata and attribution record source, licence, hashes and the split rule.
"""

import hashlib
import json
import pickle
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from backend.train_model import (  # noqa: E402
    DATA_PATH,
    META_PATH,
    MODEL_PATH,
    SOURCE_PATH,
    TEST_SIZE,
    labels,
    load_dataset,
    load_provenance,
    split_dataset,
    validate_polarity,
)
from sklearn.model_selection import train_test_split  # noqa: E402

ATTRIBUTION_PATH = ROOT / "data" / "ATTRIBUTION.md"


def feature_vectors(frame: pd.DataFrame) -> set[tuple]:
    return {tuple(row) for row in frame.itertuples(index=False, name=None)}


@pytest.fixture(scope="module")
def raw_and_unique():
    return load_dataset()


@pytest.fixture(scope="module")
def provenance():
    return load_provenance()


def test_the_file_is_the_complete_cleveland_export(raw_and_unique):
    raw, unique = raw_and_unique
    # 303 source records; the importer drops the 6 with a missing `ca`/`thal`.
    assert len(raw) == 297
    assert len(unique) == 297
    assert raw.duplicated().sum() == 0
    assert list(raw.columns) == [
        "age", "sex", "cp", "trestbps", "chol", "fbs", "restecg",
        "thalach", "exang", "oldpeak", "slope", "ca", "thal", "target",
    ]
    assert raw.isna().sum().sum() == 0
    assert set(raw["target"].unique()) == {0, 1}
    assert int(raw["target"].sum()) == 137


def test_loader_still_deduplicates_when_handed_duplicates(tmp_path):
    """The file is clean now; the loader must stay defensive anyway."""
    duplicated = pd.concat([pd.read_csv(DATA_PATH)] * 3, ignore_index=True)
    path = tmp_path / "heart_duplicated.csv"
    duplicated.to_csv(path, index=False)

    raw, unique = load_dataset(path)
    assert len(raw) == 891
    assert len(unique) == 297
    assert not unique.duplicated().any()


def test_no_feature_vector_appears_on_both_sides_of_the_split(raw_and_unique):
    _, unique = raw_and_unique
    X_train, X_test, _, _ = split_dataset(unique)
    overlap = feature_vectors(X_train) & feature_vectors(X_test)
    assert overlap == set(), f"{len(overlap)} profiles leaked from train into test"
    assert len(X_train) + len(X_test) == len(unique)


def test_splitting_duplicates_without_deduplicating_would_leak(raw_and_unique):
    """The failure mode, reproduced on synthetic duplicates: why the loader exists."""
    _, unique = raw_and_unique
    duplicated = pd.concat([unique, unique], ignore_index=True)
    y = labels(duplicated)
    X_train, X_test, _, _ = train_test_split(
        duplicated.drop("target", axis=1), y, test_size=TEST_SIZE, random_state=42, stratify=y
    )
    assert len(feature_vectors(X_train) & feature_vectors(X_test)) > 50


def test_labels_point_the_way_cardiology_does(raw_and_unique):
    _, unique = raw_and_unique
    means = validate_polarity(unique)
    assert means["thalach"]["disease"] < means["thalach"]["healthy"]
    assert means["oldpeak"]["disease"] > means["oldpeak"]["healthy"]
    assert means["ca"]["disease"] > means["ca"]["healthy"]


def test_an_inverted_file_is_rejected(raw_and_unique):
    """The Kaggle copy's defect, on a frame that has it: training must refuse."""
    _, unique = raw_and_unique
    inverted = unique.copy()
    inverted["target"] = 1 - inverted["target"]
    with pytest.raises(ValueError, match="label polarity"):
        validate_polarity(inverted)


def test_metadata_states_source_licence_split_and_counts(raw_and_unique, provenance):
    raw, unique = raw_and_unique
    meta = json.loads(META_PATH.read_text(encoding="utf-8"))

    assert meta["dataset_rows"] == len(raw)
    assert meta["dataset_unique_rows"] == len(unique)
    assert meta["dataset_duplicate_rows"] == 0
    assert meta["n_train"] + meta["n_test"] == len(unique)

    # The CSV is fingerprinted, so a swapped file is visible next to the metrics.
    assert meta["dataset_sha256"] == hashlib.sha256(DATA_PATH.read_bytes()).hexdigest()

    source = meta["dataset_source"]
    assert source["licence"] == "CC BY 4.0"
    assert "creativecommons.org/licenses/by/4.0" in source["licence_url"]
    assert "archive.ics.uci.edu" in source["url"]
    assert source["citation"] and "10.24432/C52P4X" in source["doi"]
    assert source["dropped_incomplete_rows"] == 6
    assert meta["target_encoding"].startswith("1 = disease")

    # A reviewer must be able to read how the split was made without the script.
    rule = meta["split"].lower()
    assert "duplicate" in rule and "split" in rule and "never shared" in rule


def test_provenance_file_matches_the_dataset(raw_and_unique, provenance):
    raw, _ = raw_and_unique
    assert provenance["licence"] == "CC BY 4.0"
    assert provenance["rows"] == len(raw)
    assert provenance["source_rows"] == 303
    assert provenance["dropped_incomplete_rows"] == 6
    assert provenance["unique_rows"] == len(raw)
    assert len(provenance["member_sha256"]) == 64
    assert any("binarised" in step for step in provenance["transformations"])


def test_attribution_is_shipped_with_the_data():
    """CC BY 4.0 requires attribution; deleting the notice must fail a test."""
    text = ATTRIBUTION_PATH.read_text(encoding="utf-8")
    assert "CC BY 4.0" in text
    assert "creativecommons.org/licenses/by/4.0" in text
    assert "UCI" in text and "10.24432/C52P4X" in text
    assert "Detrano" in text


def test_reported_metrics_are_bounded_and_match_the_artifact():
    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    for name in ("accuracy", "precision", "recall", "f1", "roc_auc"):
        value = meta["metrics"][name]
        assert 0.0 <= value <= 1.0, name
    assert 0.0 <= meta["metrics"]["cv_roc_auc"] <= 1.0

    with open(MODEL_PATH, "rb") as handle:
        model = pickle.load(handle)
    assert model.n_features_in_ == len(meta["features"])
