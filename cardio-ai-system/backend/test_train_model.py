"""Guards on the screening model's evidence, not on its accuracy.

The model card used to report ROC-AUC 1.000 and recall 1.000 on "1,025 rows".
Both numbers were real arithmetic over a leaked split: 723 of those 1,025 rows
were exact duplicates, so the same patient profile sat in training and in the
holdout and the forest only had to memorise it. This module pins the split rule
that replaced it, so the flattering number cannot come back by accident:

* the loader hands the splitter distinct rows only;
* no feature vector appears on both sides of the split;
* the metadata records the rule and the distinct-row counts next to the metrics.

The last test deliberately reproduces the old bug — splitting the raw file
before de-duplicating — so the guard is shown to detect the thing it exists for
rather than merely passing on repaired data.
"""

import json
import pickle
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.train_model import (  # noqa: E402
    DATA_PATH,
    META_PATH,
    MODEL_PATH,
    TEST_SIZE,
    load_dataset,
    split_dataset,
)
from sklearn.model_selection import train_test_split  # noqa: E402


def feature_vectors(frame: pd.DataFrame) -> set[tuple]:
    return {tuple(row) for row in frame.itertuples(index=False, name=None)}


@pytest.fixture(scope="module")
def raw_and_unique():
    return load_dataset()


def test_the_source_file_still_contains_duplicates(raw_and_unique):
    """If this fails the fixture changed; the rest of the file explains why it matters."""
    raw, unique = raw_and_unique
    assert len(raw) == 1025
    assert len(unique) == 302
    assert raw.duplicated().sum() == 723


def test_loader_hands_the_splitter_distinct_rows_only(raw_and_unique):
    raw, unique = raw_and_unique
    assert not unique.duplicated().any()
    assert len(unique) < len(raw)
    # De-duplication must not drop columns or rewrite labels.
    assert list(unique.columns) == list(raw.columns)
    assert set(unique["target"].unique()) <= set(raw["target"].unique())


def test_no_feature_vector_appears_on_both_sides_of_the_split(raw_and_unique):
    _, unique = raw_and_unique
    X_train, X_test, _, _ = split_dataset(unique)
    overlap = feature_vectors(X_train) & feature_vectors(X_test)
    assert overlap == set(), f"{len(overlap)} profiles leaked from train into test"
    assert len(X_train) + len(X_test) == len(unique)


def test_splitting_before_deduplicating_would_leak(raw_and_unique):
    """The old procedure, reproduced: it is why the honest numbers are lower."""
    raw, _ = raw_and_unique
    y = 1 - raw["target"]
    X_train, X_test, _, _ = train_test_split(
        raw.drop("target", axis=1), y, test_size=TEST_SIZE, random_state=42, stratify=y
    )
    leaked = feature_vectors(X_train) & feature_vectors(X_test)
    assert len(leaked) > 100, "the duplicate leak this test documents has disappeared from the data"


def test_metadata_states_the_split_rule_and_the_distinct_counts(raw_and_unique):
    raw, unique = raw_and_unique
    meta = json.loads(META_PATH.read_text(encoding="utf-8"))

    assert meta["dataset_rows"] == len(raw)
    assert meta["dataset_unique_rows"] == len(unique)
    assert meta["dataset_duplicate_rows"] == len(raw) - len(unique)
    assert meta["n_train"] + meta["n_test"] == len(unique)

    # A reviewer must be able to read how the split was made without the script.
    rule = meta["split"].lower()
    assert "duplicate" in rule and "split" in rule
    assert "leak" not in rule or "never" in rule
    assert meta["metrics_note"].strip()


def test_reported_metrics_are_bounded_and_match_the_artifact():
    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    for name in ("accuracy", "precision", "recall", "f1", "roc_auc"):
        value = meta["metrics"][name]
        assert 0.0 <= value <= 1.0, name
    assert 0.0 <= meta["metrics"]["cv_roc_auc"] <= 1.0

    with open(MODEL_PATH, "rb") as handle:
        model = pickle.load(handle)
    assert model.n_features_in_ == len(meta["features"])
