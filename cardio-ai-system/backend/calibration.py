"""Calibration of the screening probability, separate from its ranking.

ROC-AUC only says the model orders patients correctly; it says nothing about
whether the number shown to a clinician means what it appears to mean. A model
can rank perfectly and still say 0.9 for patients who turn out to be disease-free
two times in five. PulseIQ displays `probability` and bands it at 0.45 / 0.75, so
the *value* is load-bearing, not just the order: a miscalibrated probability
moves a patient into the wrong band.

Two numbers, both standard and both computed here without dependencies:

* **Brier score** — mean squared error of the probability, lower is better.
  0.25 is the score of always predicting 0.5, so anything at or above that has
  no skill on the probability scale, whatever its AUC.
* **Expected calibration error (ECE)** — bin the predictions, compare the mean
  predicted probability in each bin with the observed disease rate there, and
  average the gap weighted by bin size.

Kept pure (plain Python, no sklearn) so the arithmetic is tested directly and
the training script only has to call it.
"""

from __future__ import annotations

from typing import Sequence


def _validate(y_true: Sequence[int], y_prob: Sequence[float]) -> None:
    if len(y_true) != len(y_prob):
        raise ValueError("y_true and y_prob must be the same length")
    if not y_true:
        raise ValueError("calibration needs at least one sample")
    for probability in y_prob:
        if not 0.0 <= float(probability) <= 1.0:
            raise ValueError(f"probability out of range: {probability!r}")


def brier_score(y_true: Sequence[int], y_prob: Sequence[float]) -> float:
    """Mean squared difference between predicted probability and outcome."""
    _validate(y_true, y_prob)
    return sum((float(p) - int(y)) ** 2 for y, p in zip(y_true, y_prob)) / len(y_true)


def reliability_bins(
    y_true: Sequence[int], y_prob: Sequence[float], n_bins: int = 10
) -> list[dict]:
    """Equal-width bins over [0, 1], each with its predicted and observed rate.

    A probability of exactly 1.0 belongs to the last bin. Empty bins are kept in
    the list (with `count` 0 and `None` rates) so a caller can plot the full
    range, but they contribute nothing to ECE.
    """
    if n_bins < 1:
        raise ValueError("n_bins must be at least 1")
    _validate(y_true, y_prob)

    totals = [0] * n_bins
    predicted = [0.0] * n_bins
    observed = [0] * n_bins

    for y, p in zip(y_true, y_prob):
        p = float(p)
        index = min(int(p * n_bins), n_bins - 1)
        totals[index] += 1
        predicted[index] += p
        observed[index] += int(y)

    bins = []
    for index in range(n_bins):
        count = totals[index]
        bins.append(
            {
                "lower": index / n_bins,
                "upper": (index + 1) / n_bins,
                "count": count,
                "mean_predicted": (predicted[index] / count) if count else None,
                "observed_rate": (observed[index] / count) if count else None,
            }
        )
    return bins


def calibration_summary(
    y_true: Sequence[int], y_prob: Sequence[float], n_bins: int = 10
) -> dict:
    """Brier score, ECE and the reliability table in one dict.

    `ece` is the sample-weighted mean absolute gap between predicted and
    observed rate, i.e. how far the number in the UI is from a frequency.
    """
    _validate(y_true, y_prob)
    bins = reliability_bins(y_true, y_prob, n_bins)
    total = len(y_true)
    ece = sum(
        (entry["count"] / total) * abs(entry["mean_predicted"] - entry["observed_rate"])
        for entry in bins
        if entry["count"]
    )
    return {
        "n": total,
        "bins": n_bins,
        "brier": brier_score(y_true, y_prob),
        "ece": ece,
        "base_rate": sum(int(y) for y in y_true) / total,
        "mean_predicted": sum(float(p) for p in y_prob) / total,
        "reliability": bins,
    }


def format_reliability_table(summary: dict) -> str:
    """Plain-text reliability table, for the training log and for reviewers."""
    lines = [
        f"  {'bin':<12}{'n':>4}{'predicted':>11}{'observed':>10}{'gap':>8}",
    ]
    for entry in summary["reliability"]:
        if not entry["count"]:
            continue
        gap = entry["mean_predicted"] - entry["observed_rate"]
        lines.append(
            f"  {entry['lower']:.1f}–{entry['upper']:.1f}{'':<4}"
            f"{entry['count']:>4}{entry['mean_predicted']:>11.2f}"
            f"{entry['observed_rate']:>10.2f}{gap:>+8.2f}"
        )
    return "\n".join(lines)
