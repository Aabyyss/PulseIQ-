"""Tests for the probability scale, not the ranking.

ROC-AUC was already covered; these tests are about the number the app displays
and bands at 0.45 / 0.75. A model can rank perfectly and still say 0.9 for
patients who are disease-free half the time, so Brier score and ECE are checked
against hand-computed examples, including the case that matters most: an
overconfident model whose Brier score is quantifiably worse than a calibrated
one that makes the same predictions less sharply.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.calibration import (  # noqa: E402
    brier_score,
    calibration_summary,
    format_reliability_table,
    reliability_bins,
)
from backend.train_model import META_PATH  # noqa: E402


def test_perfect_predictions_score_zero():
    assert brier_score([0, 1, 1, 0], [0.0, 1.0, 1.0, 0.0]) == 0.0
    summary = calibration_summary([0, 1, 1, 0], [0.0, 1.0, 1.0, 0.0])
    assert summary["ece"] == 0.0


def test_brier_matches_the_hand_calculation():
    # (0 - 0.9)^2 = 0.81, (1 - 0.1)^2 = 0.81 -> mean 0.81
    assert brier_score([0, 1], [0.9, 0.1]) == pytest.approx(0.81)
    # The no-skill reference: always saying 0.5 scores 0.25 regardless of labels.
    assert brier_score([0, 1, 1, 0], [0.5] * 4) == pytest.approx(0.25)


def test_ece_matches_the_hand_calculation():
    # Ten patients predicted at 0.2, four of them actually diseased:
    # |0.2 - 0.4| = 0.2, and the one bin holds the whole sample.
    summary = calibration_summary([1, 1, 1, 1, 0, 0, 0, 0, 0, 0], [0.2] * 10)
    assert summary["ece"] == pytest.approx(0.2)
    assert summary["bins"] == 10

    # A perfectly calibrated constant prediction has no calibration error even
    # when it is not confident: ECE measures the gap, not the sharpness.
    summary = calibration_summary([1, 1, 1, 0, 0, 0, 0, 0, 0, 0], [0.3] * 10)
    assert summary["ece"] == pytest.approx(0.0)


def test_overconfidence_costs_more_than_a_calibrated_forecast():
    """The failure ECE exists to catch: right ordering, wrong probabilities."""
    labels = [1, 1, 0, 0]
    calibrated = [0.5, 0.5, 0.5, 0.5]
    overconfident = [0.99, 0.01, 0.99, 0.01]  # two of four are confidently wrong

    assert brier_score(labels, overconfident) > brier_score(labels, calibrated)
    assert calibration_summary(labels, overconfident)["ece"] > calibration_summary(
        labels, calibrated
    )["ece"]


def test_bins_cover_every_sample_and_hold_probability_one_in_the_last_bin():
    probabilities = [0.0, 0.05, 0.5, 0.999, 1.0]
    bins = reliability_bins([0, 0, 1, 1, 1], probabilities, n_bins=10)
    assert sum(entry["count"] for entry in bins) == len(probabilities)
    assert bins[0]["count"] == 2  # 0.0 and 0.05
    assert bins[-1]["count"] == 2  # 0.999 and exactly 1.0
    assert bins[-1]["upper"] == 1.0


def test_empty_bins_are_kept_but_do_not_affect_ece():
    bins = reliability_bins([0, 1], [0.05, 0.95], n_bins=10)
    assert [entry["count"] for entry in bins].count(0) == 8
    # One patient per occupied bin cannot hit its own predicted rate: 0.05 vs
    # 0 and 0.95 vs 1 are each a 0.05 gap, so ECE is 0.05, not 0. Empty bins
    # contribute nothing either way — that is what this asserts.
    assert calibration_summary([0, 1], [0.05, 0.95])["ece"] == pytest.approx(0.05)
    assert calibration_summary([0, 1], [0.0, 1.0])["ece"] == pytest.approx(0.0)


def test_rejects_impossible_input():
    with pytest.raises(ValueError):
        brier_score([0, 1], [0.5])
    with pytest.raises(ValueError):
        brier_score([], [])
    with pytest.raises(ValueError):
        brier_score([0, 1], [0.5, 1.2])
    with pytest.raises(ValueError):
        brier_score([0, 1], [-0.1, 0.5])
    with pytest.raises(ValueError):
        reliability_bins([0, 1], [0.5, 0.5], n_bins=0)


def test_reliability_table_skips_empty_bins():
    table = format_reliability_table(calibration_summary([0, 1], [0.05, 0.95]))
    assert "predicted" in table and "observed" in table
    assert len([line for line in table.splitlines() if line.strip()]) == 3  # header + 2 bins


def test_the_recorded_model_publishes_its_calibration():
    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    calibration = meta["calibration"]
    out_of_fold = calibration["out_of_fold"]

    # One out-of-fold prediction per distinct patient — the deduplicated count.
    assert out_of_fold["n"] == meta["dataset_unique_rows"] == 302
    assert 0.0 <= out_of_fold["brier"] < 0.25, "no better than always predicting 0.5"
    assert 0.0 <= out_of_fold["ece"] <= 1.0
    assert 0.0 <= out_of_fold["base_rate"] <= 1.0

    # The reliability table is published too, so a reviewer can redraw the plot.
    reliability = calibration["reliability"]
    assert len(reliability) == out_of_fold["bins"] == 10
    assert sum(entry["count"] for entry in reliability) == out_of_fold["n"]
    assert "out-of-fold" in meta["metrics_note"]
