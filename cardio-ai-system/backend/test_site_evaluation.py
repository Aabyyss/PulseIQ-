"""Per-site evaluation: the missingness, the imputation source, the arithmetic.

The other three UCI cohorts are nearly unusable for this feature vector — one
complete Hungarian record, none in Switzerland, one in VA — so the honest way to
report them is all-rows-with-imputation plus a low-imputation subset, with the
missing counts published beside the metrics. These tests pin each of those
choices, and in particular that imputation comes from the Cleveland *training*
split and never from the site being scored: filling a Swiss cholesterol from
Swiss rows would be leakage dressed as preprocessing.
"""

import pickle
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from backend import site_evaluation as evaluation  # noqa: E402
from backend.train_model import MODEL_PATH, load_dataset, split_dataset  # noqa: E402


@pytest.fixture(scope="module")
def rows():
    return evaluation.load_site_rows()


@pytest.fixture(scope="module")
def model():
    with open(MODEL_PATH, "rb") as handle:
        return pickle.load(handle)


@pytest.fixture(scope="module")
def statistics():
    return evaluation.training_imputation()


def by_site(rows, site):
    return [row for row in rows if row["site"] == site]


def test_all_four_sites_are_imported(rows):
    counts = {site: len(by_site(rows, site)) for site in evaluation.SITE_ORDER}
    assert counts == {"cleveland": 303, "hungarian": 294, "switzerland": 123, "va": 200}
    assert len(rows) == 920
    assert {row["site"] for row in rows} == set(evaluation.SITE_ORDER)
    assert {row["target"] for row in rows} == {0, 1}


def test_missingness_matches_the_source(rows):
    """These counts are the reason complete-case evaluation is not an option."""
    complete = {
        site: sum(
            1
            for row in by_site(rows, site)
            if all(value is not None for value in row["features"].values())
        )
        for site in evaluation.SITE_ORDER
    }
    assert complete == {"cleveland": 297, "hungarian": 1, "switzerland": 0, "va": 1}

    def missing(site, column):
        return sum(1 for row in by_site(rows, site) if row["features"][column] is None)

    assert missing("hungarian", "ca") == 291
    assert missing("hungarian", "thal") == 266
    assert missing("hungarian", "slope") == 190
    assert missing("va", "ca") == 198
    assert missing("va", "thal") == 166


def test_cholesterol_zero_is_treated_as_missing_not_as_zero(rows):
    """Every Swiss record encodes an unmeasured cholesterol as 0."""
    swiss = by_site(rows, "switzerland")
    assert all(row["features"]["chol"] is None for row in swiss)
    assert sum(row["sentinel_zeros"] for row in swiss) == 123

    va = by_site(rows, "va")
    # 49 placeholder zeros plus the 7 records that were already blank.
    assert sum(1 for row in va if row["features"]["chol"] is None) == 56
    # A real zero oldpeak must survive: zero ST depression is a finding.
    assert sum(1 for row in by_site(rows, "cleveland") if row["features"]["oldpeak"] == 0.0) > 0


def test_imputation_is_fitted_on_the_cleveland_training_split(statistics):
    values, training_rows = statistics
    _, data = load_dataset()
    X_train = split_dataset(data)[0]

    assert training_rows == len(X_train) == 237
    for column in evaluation.FEATURES:
        expected = (
            float(X_train[column].mode().iloc[0])
            if column in evaluation.CATEGORICAL
            else float(X_train[column].median())
        )
        assert values[column] == pytest.approx(expected)


def test_impute_fills_every_missing_field_and_counts_them(statistics):
    values, _ = statistics
    all_missing = {column: None for column in evaluation.FEATURES}
    vector, filled = evaluation.impute(all_missing, values)
    assert filled == len(evaluation.FEATURES)
    assert vector == [values[column] for column in evaluation.FEATURES]

    complete = {column: 1.0 for column in evaluation.FEATURES}
    vector, filled = evaluation.impute(complete, values)
    assert filled == 0
    assert vector == [1.0] * len(evaluation.FEATURES)


class ConstantModel:
    """Predicts a fixed probability so the metric arithmetic is checkable."""

    def __init__(self, probability):
        self.probability = probability

    def predict_proba(self, frame):
        probability = self.probability
        return np.array([[1 - probability, probability] for _ in range(len(frame))])


def test_metrics_are_bounded_and_single_class_has_no_auc(statistics):
    values, _ = statistics
    rows = [
        {"site": "va", "features": {c: 1.0 for c in evaluation.FEATURES}, "target": 1,
         "sentinel_zeros": 0},
    ]
    scored = evaluation.score_rows(rows, ConstantModel(0.5), values)
    assert scored["n"] == 1
    assert scored["metrics"]["roc_auc"] is None  # one class: AUC undefined
    assert scored["metrics"]["brier"] == pytest.approx(0.25)
    assert scored["imputed_values"] == 0


def test_low_imputation_subset_is_smaller_or_equal_and_needs_fewer_fills(rows, model, statistics):
    values, _ = statistics
    hungarian = by_site(rows, "hungarian")

    all_rows = evaluation.score_rows(hungarian, model, values)
    low = evaluation.score_rows(hungarian, model, values, max_imputed=2)

    assert low["n"] <= all_rows["n"]
    assert low["imputed_values"] <= all_rows["imputed_values"]
    # The restriction exists to keep the filled-feature count down, so it must.
    assert low["mean_imputed_per_row"] <= all_rows["mean_imputed_per_row"]
    assert low["mean_imputed_per_row"] <= 2


def test_report_separates_the_holdout_from_external_sites(rows, model, statistics):
    values, training_rows = statistics
    report = evaluation.build_report(model, values, training_rows)

    cleveland = report["sites"]["cleveland"]
    assert "internal_holdout" in cleveland
    assert "all_rows" not in cleveland, "scoring Cleveland's training rows would be self-assessment"
    assert cleveland["internal_holdout"]["n"] == 60

    for site in ("hungarian", "switzerland", "va"):
        block = report["sites"][site]
        assert block["rows"] == len(by_site(rows, site))
        assert block["all_rows"]["n"] == block["rows"]
        assert block["low_imputation"]["n"] <= block["all_rows"]["n"]
        assert 0.0 <= block["all_rows"]["metrics"]["brier"] <= 1.0
        assert 0.0 <= block["disease_rate"] <= 1.0


def test_report_states_the_imputation_source(rows, model, statistics):
    values, training_rows = statistics
    report = evaluation.build_report(model, values, training_rows)
    assert "Cleveland training split" in report["imputation"]["source"]
    assert report["imputation"]["low_imputation_limit"] == 2
    assert "chol" in report["imputation"]["values"]


def test_committed_report_is_present_and_complete():
    import json

    report = json.loads(evaluation.REPORT_PATH.read_text(encoding="utf-8"))
    assert set(report["sites"]) == set(evaluation.SITE_ORDER)
    assert report["sites"]["hungarian"]["all_rows"]["metrics"]["roc_auc"] is not None
