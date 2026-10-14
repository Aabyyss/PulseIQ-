"""The published tables the deterministic scores are built from, pinned.

Why this file exists
--------------------
``agents/risk_scores_agent.py`` implements HEART, GRACE, CHA₂DS₂-VASc and the 2013
ACC/AHA Pooled Cohort Equations, and its module docstring quotes the source of
each one. Everything in those instruments that is *transcribed* — point tables,
band cut-offs, nomogram mortality rows, coefficients — is invisible to the rest of
the suite: the behavioural tests agree with whatever the tables say, because they
read the same tables. A digit that drifts, or a row that is retyped one place too
high, would pass every one of them and quietly change a patient's score.

So the tables are written out again below, from the published sources, and
compared row by row. A drifted value fails here with the source named.

Re-verifying (read the source — never edit this file to match the code):
- **HEART** (Backus et al. 2008): component points, the 0-3 / 4-6 / 7-10 bands and
  the published 6-week MACE ranges, as summarised at
  https://www.mdcalc.com/calc/1752/heart-score-major-cardiac-events
- **GRACE** (Granger et al., Arch Intern Med 2003;163:2345): the admission point
  bins, the Killip and admission-finding points, the low/intermediate/high bands
  and the in-hospital mortality nomogram, reproduced at
  https://www.wikidoc.org/index.php/The_GRACE_risk_score

The thresholds that are *conventions* of this implementation rather than published
quantities (how a chest-pain history is called typical, how serum creatinine is
converted) are asserted in ``backend/test_risk_scores.py``, where the reasoning
behind them lives.

Runnable via pytest and directly (``python backend/test_score_sources.py``).
"""

import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents import risk_scores_agent  # noqa: E402
from agents.risk_scores_agent import grace_score, heart_score  # noqa: E402


# ---------------------------------------------------------------------------
# HEART — Backus et al. 2008 (mdcalc.com/calc/1752)
# ---------------------------------------------------------------------------

# History: slightly suspicious 0, moderately suspicious 1, highly suspicious 2.
HEART_HISTORY_POINTS = {"non_specific": 0, "atypical": 1, "typical": 2}
# ECG: normal 0, non-specific repolarisation changes 1, significant ST deviation 2.
HEART_ECG_POINTS = {"normal": 0, "repolarisation": 1, "st_deviation": 2}
# Age: <45 = 0, 45-64 = 1, >=65 = 2. Risk factors: none 0, 1-2 = 1,
# >=3 or known atherosclerotic disease 2. Troponin: at or below the assay's
# upper limit 0, 1-3x 1, >3x 2. Those three are asserted below at their
# boundaries rather than as a table, because they are ranges, not rows.
# Score bands: 0-3 low, 4-6 intermediate, 7-10 high.
HEART_BANDS = [(3, "low"), (6, "intermediate"), (10, "high")]
# 6-week MACE as published for each band (the ranges mdcalc prints).
HEART_MACE_RANGES = {"low": "0.9-1.7%", "intermediate": "12-16.6%", "high": "50-65%"}


def _heart(**overrides) -> dict:
    """A 50-year-old with a typical history, a normal ECG and a normal troponin."""
    base = dict(history="typical", ecg="normal", age=50, risk_factor_count=0, troponin_ratio=0.5)
    base.update(overrides)
    return heart_score(**base)


def test_heart_component_tables_match_the_published_score():
    assert risk_scores_agent._HISTORY_POINTS == HEART_HISTORY_POINTS
    assert risk_scores_agent._ECG_POINTS == HEART_ECG_POINTS


def test_heart_age_risk_factor_and_troponin_boundaries_are_published_ones():
    """The three items that are ranges: each boundary is asserted where it sits."""
    for age, want in ((44, 0), (45, 1), (64, 1), (65, 2), (90, 2)):
        assert _heart(age=age)["components"]["age"]["points"] == want, age
    for count, want in ((0, 0), (1, 1), (2, 1), (3, 2), (6, 2)):
        assert _heart(risk_factor_count=count)["components"]["risk_factors"]["points"] == want, count
    # Established atherosclerotic disease scores the full 2 regardless of the count.
    assert _heart(risk_factor_count=0, established_ascvd=True)["components"]["risk_factors"]["points"] == 2
    for ratio, want in ((0.5, 0), (1.0, 0), (1.01, 1), (3.0, 1), (3.01, 2), (12.0, 2)):
        assert _heart(troponin_ratio=ratio)["components"]["troponin"]["points"] == want, ratio


def test_heart_bands_and_six_week_mace_ranges_match_the_published_score():
    assert risk_scores_agent._HEART_BANDS == HEART_BANDS
    assert risk_scores_agent.HEART_MACE_RATES == HEART_MACE_RANGES

    # Each total is built from the published point values, so it lands on the band
    # boundary the source puts it on: 3 is the last low total, 4 the first
    # intermediate, 6 the last intermediate, 7 the first high.
    boundaries = [
        (dict(history="typical", ecg="repolarisation", age=40, risk_factor_count=0), 3, "low"),
        (dict(history="typical", ecg="repolarisation", age=40, risk_factor_count=1), 4, "intermediate"),
        (dict(history="typical", ecg="st_deviation", age=50, risk_factor_count=1), 6, "intermediate"),
        (dict(history="typical", ecg="st_deviation", age=70, risk_factor_count=1), 7, "high"),
    ]
    for inputs, want_score, want_band in boundaries:
        score = _heart(troponin_ratio=0.5, **inputs)
        assert score["score"] == want_score, inputs
        assert score["band"] == want_band, inputs
        assert score["mace_risk_6_weeks"] == HEART_MACE_RANGES[want_band], inputs
    # The total is the sum of the component maxima: 2 + 2 + 2 + 2 + 2.
    assert _heart(history="typical", ecg="st_deviation", age=70, risk_factor_count=3, troponin_ratio=4.0)["max_score"] == 10


# ---------------------------------------------------------------------------
# GRACE, classic in-hospital score — Granger et al. 2003 (wikidoc reproduction)
# ---------------------------------------------------------------------------

# (inclusive upper bound, points); the last tuple of each table is the open top bin.
GRACE_AGE = [(29, 0), (39, 8), (49, 25), (59, 41), (69, 58), (79, 75), (89, 91), (10 ** 9, 100)]
GRACE_HEART_RATE = [(49, 0), (69, 3), (89, 9), (109, 15), (149, 24), (199, 38), (10 ** 9, 46)]
GRACE_SYSTOLIC = [(79, 58), (99, 53), (119, 43), (139, 34), (159, 24), (199, 10), (10 ** 9, 0)]
GRACE_CREATININE = [(0.399, 1), (0.799, 4), (1.199, 7), (1.599, 10), (1.999, 13), (3.999, 21), (10 ** 9, 28)]
GRACE_KILLIP = {"I": 0, "II": 20, "III": 39, "IV": 59}
# Admission findings: arrest at admission, ST-segment deviation, raised enzymes.
GRACE_ADMISSION_POINTS = {"cardiac_arrest": 39, "st_deviation": 28, "elevated_markers": 14}
# Every component at its maximum: 100 + 46 + 58 + 28 + 59 + 39 + 28 + 14.
GRACE_MAXIMUM = 372
# Risk bands: <109 low, 109-140 intermediate, >140 high.
GRACE_BANDS = [(108, "low"), (140, "intermediate"), (float("inf"), "high")]
# The published in-hospital mortality nomogram: printed score ticks and the
# probability each one gives.
GRACE_MORTALITY_ROWS = [
    (60, 0.2), (70, 0.3), (80, 0.4), (90, 0.6), (100, 0.8), (110, 1.1),
    (120, 1.6), (130, 2.1), (140, 2.9), (150, 3.9), (160, 5.4), (170, 7.3),
    (180, 9.8), (190, 13.0), (200, 18.0), (210, 23.0), (220, 29.0), (230, 36.0),
    (240, 44.0), (250, 52.0),
]


def _grace(**overrides) -> dict:
    """A 45-year-old with a normal rate, a normal pressure and 1 mg/dL creatinine."""
    base = dict(
        age=45, heart_rate=60, systolic_bp=110, creatinine_mg_dl=1.0, killip="I",
        cardiac_arrest=False, st_deviation=False, elevated_markers=False,
    )
    base.update(overrides)
    return grace_score(**base)


def test_grace_point_tables_match_the_published_score():
    assert risk_scores_agent._GRACE_AGE == GRACE_AGE
    assert risk_scores_agent._GRACE_HEART_RATE == GRACE_HEART_RATE
    assert risk_scores_agent._GRACE_SYSTOLIC == GRACE_SYSTOLIC
    assert risk_scores_agent._GRACE_CREATININE == GRACE_CREATININE
    assert risk_scores_agent._GRACE_KILLIP == GRACE_KILLIP
    assert GRACE_MAXIMUM == 100 + 46 + 58 + 28 + 59 + 39 + 28 + 14
    assert risk_scores_agent.GRACE_MAX_SCORE == GRACE_MAXIMUM


def test_grace_admission_findings_are_worth_the_published_points():
    baseline = _grace()
    for item, points in GRACE_ADMISSION_POINTS.items():
        assert baseline["components"][item]["points"] == 0, item
        with_finding = _grace(**{item: True})
        assert with_finding["components"][item]["points"] == points, item
        assert with_finding["score"] - baseline["score"] == points, item


def test_grace_bands_match_the_published_cut_offs():
    assert risk_scores_agent._GRACE_BANDS == GRACE_BANDS

    # Each case sums to its total through the published bins, so the band is read
    # at the cut-off itself: 108 is the last low total, 109 the first intermediate,
    # 140 the last intermediate, 141 the first high.
    #   108 = 58 (age 65) + 0 (rate 45) + 43 (SBP 110) + 7 (creatinine 1.0)
    #   109 = 75 (age 75) + 0 (rate 45) + 24 (SBP 150) + 10 (creatinine 1.4)
    #   140 = 58 (age 65) + 15 (rate 100) + 24 (SBP 150) + 4 (creatinine 0.5) + 39 (arrest)
    #   141 = 91 (age 85) + 3 (rate 60) + 43 (SBP 110) + 4 (creatinine 0.5)
    cases = [
        (dict(age=65, heart_rate=45, systolic_bp=110, creatinine_mg_dl=1.0), 108, "low"),
        (dict(age=75, heart_rate=45, systolic_bp=150, creatinine_mg_dl=1.4), 109, "intermediate"),
        (dict(age=65, heart_rate=100, systolic_bp=150, creatinine_mg_dl=0.5, cardiac_arrest=True), 140, "intermediate"),
        (dict(age=85, heart_rate=60, systolic_bp=110, creatinine_mg_dl=0.5), 141, "high"),
    ]
    for inputs, want_score, want_band in cases:
        score = _grace(**inputs)
        assert score["score"] == want_score, inputs
        assert score["band"] == want_band, inputs


def test_grace_mortality_rows_are_the_published_nomogram():
    assert risk_scores_agent._GRACE_MORTALITY_TABLE == GRACE_MORTALITY_ROWS

    # Every printed row is returned as printed, not interpolated.
    for printed_score, percent in GRACE_MORTALITY_ROWS:
        row = risk_scores_agent._grace_mortality_from_table(printed_score)
        assert (row["percent"], row["interpolated"]) == (percent, False), printed_score
        assert str(printed_score) in row["anchor"], printed_score
    # Below and above the table the outermost printed value is the anchor...
    assert risk_scores_agent._grace_mortality_from_table(40)["percent"] == 0.2
    assert risk_scores_agent._grace_mortality_from_table(400)["percent"] == 52.0
    # ...and a score between two rows is an interpolation between them, labelled so.
    midway = risk_scores_agent._grace_mortality_from_table(185)
    assert midway["interpolated"] is True
    assert 9.8 < midway["percent"] < 13.0
    assert midway["anchor"] == "180 -> 9.8%, 190 -> 13%"


def main() -> None:
    """Run the suite directly (no pytest needed)."""
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_") and callable(fn)]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"[PASS] {name}")
        except AssertionError as exc:
            failures.append(name)
            print(f"[FAIL] {name}: {exc}")
    if failures:
        print(f"\n{len(failures)} failure(s): {', '.join(failures)}")
        sys.exit(1)
    print(f"\nAll {len(tests)} source-pinning cases passed.")


if __name__ == "__main__":
    main()
