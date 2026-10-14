"""Deterministic cardiac risk scores: HEART, GRACE, CHA₂DS₂-VASc, ASCVD.

Why this module exists
----------------------
Until now the urgency of an encounter was hand-derived inside the medication
layer ("chest pain is present, so call it an emergency") and the diagnosis layer
reported a model probability band. Both are defensible, but neither is a
*score*: a clinician cannot check the reasoning against a published instrument,
and two layers can disagree about the same patient.

These four scores are pure arithmetic over captured facts — no model, no LLM,
no randomness — so the same input always yields the same number, and every point
can be traced to the fact that produced it.

What is deliberately *not* here
-------------------------------
- **No guessing.** An unknown input is never treated as normal. A score with a
  missing component reports ``complete: false``, ``score: None`` (plus
  ``known_points``) and names what is missing, because a falsely low score is
  worse than no score. Clinicians fill the gap; the caller shows it.
- **No prescribing.** CHA₂DS₂-VASc carries the stroke risk and the conventional
  anticoagulation tier, never an order.
- **No diagnosis.** HEART and GRACE estimate the risk of a cardiac event in a
  patient whose presentation already suggests one; ASCVD estimates the ten-year
  risk of a first event in a patient who has *not* had one; none of them
  diagnose.

Sources (implemented literally from these):
- HEART: Backus et al. 2008; component definitions and 6-week MACE bands as
  published and summarised at https://www.mdcalc.com/calc/1752/heart-score-major-cardiac-events
  (low 0–3 ≈ 0.9–1.7%, intermediate 4–6 ≈ 12–16.6%, high 7–10 ≈ 50–65%).
- GRACE (in-hospital, classic point score): Granger et al., Arch Intern Med
  2003;163:2345 — point tables reproduced at
  https://www.wikidoc.org/index.php/The_GRACE_risk_score ; risk bands
  (<109 low, 109–140 intermediate, >140 high) as used in ACS guidance.
- CHA₂DS₂-VASc: Lip et al. 2010; values and annual stroke-risk table as
  summarised at https://www.mdcalc.com/calc/801/cha2ds2-vasc-score-atrial-fibrillation-stroke-risk
- ASCVD (2013 ACC/AHA Pooled Cohort Equations): Goff et al., Circulation
  2014;129(25 Suppl 2):S49 — coefficients, group centering values and baseline
  survival as carried by the reference implementation in the ``PooledCohort`` R
  package (https://github.com/cran/PooledCohort, ``R/predict_risk.R``), whose
  own worked example reproduces the values asserted in the tests here.
"""

from __future__ import annotations

import math
from typing import Any

# ---------------------------------------------------------------------------
# HEART
# ---------------------------------------------------------------------------

# Machine-readable strings stay ASCII: they travel through JSON, logs and a
# Windows console, so no arrows or en-dashes here.
HEART_MACE_RATES = {
    "low": "0.9-1.7%",  # score 0-3
    "intermediate": "12-16.6%",  # score 4-6
    "high": "50-65%",  # score 7-10
}

HEART_SOURCE = (
    "HEART score (Backus et al. 2008) — 6-week MACE as published "
    "(low 0–3, intermediate 4–6, high 7–10)."
)

_HISTORY_POINTS = {"non_specific": 0, "atypical": 1, "typical": 2}
_ECG_POINTS = {"normal": 0, "repolarisation": 1, "st_deviation": 2}
# The published score bands (inclusive upper bound, label). Named rather than
# written into the call, because a band is a published quantity like a point
# value and is pinned against its source by backend/test_score_sources.py.
_HEART_BANDS: list[tuple[float, str]] = [(3, "low"), (6, "intermediate"), (10, "high")]


def _band_from_cutoffs(value: float, cutoffs: list[tuple[float, str]]) -> str:
    """First label whose inclusive upper bound the value does not exceed."""
    for limit, label in cutoffs:
        if value <= limit:
            return label
    return cutoffs[-1][1]


def heart_score(
    *,
    history: str | None,
    ecg: str | None,
    age: int | None,
    risk_factor_count: int | None = None,
    established_ascvd: bool = False,
    troponin_ratio: float | None = None,
) -> dict[str, Any]:
    """HEART score for chest pain (0–10).

    ``history`` is the clinician's read of the presentation — ``"typical"``
    (traditional ACS features), ``"atypical"`` (mixed) or ``"non_specific"``.
    ``ecg`` is ``"normal"``, ``"repolarisation"`` (non-specific changes, no
    significant ST depression) or ``"st_deviation"`` (new, or of unknown age).
    ``troponin_ratio`` is the assay value divided by that assay's reference
    ceiling, so 0–1× scores 0, >1–3× scores 1 and >3× scores 2.

    ``established_ascvd`` (prior MI, prior revascularisation, PAD or stroke)
    scores the full 2 points regardless of the risk-factor count.
    """
    components: dict[str, dict[str, Any]] = {}
    missing: list[str] = []

    if history in _HISTORY_POINTS:
        components["history"] = {
            "points": _HISTORY_POINTS[history],
            "detail": {
                "typical": "presentation specific for ACS",
                "atypical": "mixed typical and atypical features",
                "non_specific": "features non-specific for ACS",
            }[history],
        }
    else:
        missing.append("history typicality")

    if ecg in _ECG_POINTS:
        components["ecg"] = {
            "points": _ECG_POINTS[ecg],
            "detail": {
                "normal": "ECG normal",
                "repolarisation": "repolarisation changes without significant ST deviation",
                "st_deviation": "significant ST deviation, new or of unknown age",
            }[ecg],
        }
    else:
        missing.append("ECG")

    if age is None:
        missing.append("age")
    else:
        points = 0 if age < 45 else (1 if age < 65 else 2)
        components["age"] = {"points": points, "detail": f"{age} years"}

    if risk_factor_count is None and not established_ascvd:
        missing.append("risk factors")
    else:
        count = risk_factor_count or 0
        if established_ascvd:
            points = 2
            detail = "established atherosclerotic disease (prior MI, revascularisation, PAD or stroke)"
        else:
            points = 0 if count == 0 else (1 if count <= 2 else 2)
            detail = f"{count} risk factor(s)"
        components["risk_factors"] = {"points": points, "detail": detail}

    if troponin_ratio is None:
        missing.append("troponin")
    else:
        if troponin_ratio <= 1.0:
            points, detail = 0, "at or below the assay's reference ceiling"
        elif troponin_ratio <= 3.0:
            points, detail = 1, "1–3× the reference ceiling"
        else:
            points, detail = 2, ">3× the reference ceiling"
        components["troponin"] = {"points": points, "detail": detail}

    known_points = sum(item["points"] for item in components.values())
    complete = not missing
    score = known_points if complete else None
    band = _band_from_cutoffs(score, _HEART_BANDS) if complete else None

    return {
        "name": "HEART",
        "score": score,
        "known_points": known_points,
        "max_score": 10,
        "complete": complete,
        "band": band,
        "components": components,
        "mace_risk_6_weeks": HEART_MACE_RATES.get(band) if band else None,
        "missing": missing,
        "source": HEART_SOURCE,
    }


# ---------------------------------------------------------------------------
# GRACE (in-hospital mortality, classic point score)
# ---------------------------------------------------------------------------

# (upper bound inclusive, points) per input; the last tuple of each list is the
# open-ended top bin.
_GRACE_AGE = [(29, 0), (39, 8), (49, 25), (59, 41), (69, 58), (79, 75), (89, 91), (10 ** 9, 100)]
_GRACE_HEART_RATE = [(49, 0), (69, 3), (89, 9), (109, 15), (149, 24), (199, 38), (10 ** 9, 46)]
_GRACE_SYSTOLIC = [(79, 58), (99, 53), (119, 43), (139, 34), (159, 24), (199, 10), (10 ** 9, 0)]
_GRACE_CREATININE = [(0.399, 1), (0.799, 4), (1.199, 7), (1.599, 10), (1.999, 13), (3.999, 21), (10 ** 9, 28)]
_GRACE_KILLIP = {"I": 0, "II": 20, "III": 39, "IV": 59}

GRACE_MAX_SCORE = 372
# Published risk bands (inclusive upper bound, label): <109 low, 109-140
# intermediate, >140 high. Named for the same reason as HEART's.
_GRACE_BANDS: list[tuple[float, str]] = [(108, "low"), (140, "intermediate"), (float("inf"), "high")]
GRACE_SOURCE = (
    "GRACE in-hospital mortality, classic point score (Granger et al., Arch Intern Med 2003) — "
    "points summed over admission values."
)

# Published nomogram reference values (score → estimated in-hospital mortality).
_GRACE_MORTALITY_TABLE: list[tuple[int, float]] = [
    (60, 0.2), (70, 0.3), (80, 0.4), (90, 0.6), (100, 0.8), (110, 1.1),
    (120, 1.6), (130, 2.1), (140, 2.9), (150, 3.9), (160, 5.4), (170, 7.3),
    (180, 9.8), (190, 13.0), (200, 18.0), (210, 23.0), (220, 29.0), (230, 36.0),
    (240, 44.0), (250, 52.0),
]


def _grace_mortality_from_table(score: int) -> dict[str, Any]:
    """Mortality from the published nomogram table, interpolated between rows.

    The original model published a nomogram, not a closed-form equation, so any
    value between two printed rows is an interpolation — and it is labelled as
    one rather than presented as a quoted figure.
    """
    if score <= _GRACE_MORTALITY_TABLE[0][0]:
        anchor = _GRACE_MORTALITY_TABLE[0]
        return {"percent": anchor[1], "interpolated": False, "anchor": f"score <={anchor[0]} -> {anchor[1]:g}%"}
    if score >= _GRACE_MORTALITY_TABLE[-1][0]:
        anchor = _GRACE_MORTALITY_TABLE[-1]
        return {"percent": anchor[1], "interpolated": False, "anchor": f"score >={anchor[0]} -> {anchor[1]:g}%"}
    for (low_score, low_pct), (high_score, high_pct) in zip(_GRACE_MORTALITY_TABLE, _GRACE_MORTALITY_TABLE[1:]):
        if low_score <= score <= high_score:
            span = high_score - low_score
            fraction = (score - low_score) / span
            percent = round(low_pct + fraction * (high_pct - low_pct), 2)
            return {
                "percent": percent,
                "interpolated": score not in (low_score, high_score),
                "anchor": f"{low_score} -> {low_pct:g}%, {high_score} -> {high_pct:g}%",
            }
    return {"percent": None, "interpolated": False, "anchor": "outside the published table"}


def grace_score(
    *,
    age: int | None,
    heart_rate: int | None,
    systolic_bp: int | None,
    creatinine_mg_dl: float | None,
    killip: str | None,
    cardiac_arrest: bool | None,
    st_deviation: bool | None,
    elevated_markers: bool | None,
) -> dict[str, Any]:
    """GRACE in-hospital mortality score: points summed, then banded and mapped.

    ``creatinine_mg_dl`` must already be in mg/dL — the classic point table is
    expressed there, and the caller converts µmol/L rather than binning it as if
    it were mg/dL. ``killip`` is ``"I".."IV"``; ``cardiac_arrest`` means arrest at
    admission; ``elevated_markers`` is the binary item for raised cardiac
    enzymes, not a troponin value.
    """
    components: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    bins = (
        ("age", _GRACE_AGE, age, "years"),
        ("heart_rate", _GRACE_HEART_RATE, heart_rate, "beats/min"),
        ("systolic_bp", _GRACE_SYSTOLIC, systolic_bp, "mmHg"),
        ("creatinine", _GRACE_CREATININE, creatinine_mg_dl, "mg/dL"),
    )
    for name, table, value, unit in bins:
        if value is None:
            missing.append(name)
            continue
        points = next(points for limit, points in table if value <= limit)
        components[name] = {"points": points, "detail": f"{value:g} {unit}"}

    killip_key = (killip or "").strip().upper().replace("CLASS", "").replace("KILLIP", "").strip()
    if killip_key in _GRACE_KILLIP:
        components["killip"] = {"points": _GRACE_KILLIP[killip_key], "detail": f"Killip class {killip_key}"}
    else:
        missing.append("Killip class")

    for name, flag, points, detail in (
        ("cardiac_arrest", cardiac_arrest, 39, "cardiac arrest at admission"),
        ("st_deviation", st_deviation, 28, "ST-segment deviation"),
        ("elevated_markers", elevated_markers, 14, "raised cardiac enzymes/markers"),
    ):
        if flag is None:
            missing.append(name)
            continue
        components[name] = {"points": points if flag else 0, "detail": detail if flag else f"no {detail}"}

    known_points = sum(item["points"] for item in components.values())
    complete = not missing
    score = known_points if complete else None
    band = None
    mortality: dict[str, Any] | None = None
    if complete:
        band = _band_from_cutoffs(score, _GRACE_BANDS)
        mortality = _grace_mortality_from_table(score)

    if mortality is None:
        note = "Mortality requires every input."
    elif mortality["interpolated"]:
        note = "Mortality is interpolated between printed rows of the published GRACE nomogram table."
    else:
        note = "Mortality is a printed value from the published GRACE nomogram table."

    return {
        "name": "GRACE",
        "score": score,
        "known_points": known_points,
        "max_score": GRACE_MAX_SCORE,
        "complete": complete,
        "band": band,
        "in_hospital_mortality": mortality,
        "components": components,
        "missing": missing,
        "source": GRACE_SOURCE,
        "note": note,
    }


# ---------------------------------------------------------------------------
# CHA₂DS₂-VASc
# ---------------------------------------------------------------------------

# Score → annual stroke risk (percent), from the published adjusted-rate table
# for untreated patients (reproduced by Medscape and UW Medicine from the
# Euro Heart Survey analysis). Two honest caveats: the series is NOT monotonic
# at the top (score 8 reads lower than score 7), and rival publications print
# different rates for the same score (the original-study annualised series in
# Lip et al., Chest 2010 gives 11.1% at score 8). So the number is reported as a
# published table value beside the source, never as an individual prediction —
# and never at all for an incomplete score.
CHA2DS2_VASC_STROKE_RISK = {
    0: 0.0, 1: 1.3, 2: 2.2, 3: 3.2, 4: 4.0,
    5: 6.7, 6: 9.8, 7: 9.6, 8: 6.7, 9: 15.2,
}

CHA2DS2_VASC_SOURCE = (
    "CHA₂DS₂-VASc (Lip et al., Chest 2010) — annual stroke risk from the published "
    "adjusted-rate table for untreated patients, which is cohort-dependent and not "
    "monotonic at the top scores; anticoagulation tiers follow the conventional "
    "ESC/ACC reading of the score."
)


def cha2ds2_vasc(
    *,
    age: int | None,
    sex: str | None,
    heart_failure: bool | None = False,
    hypertension: bool | None = False,
    diabetes: bool | None = False,
    stroke_tia: bool | None = False,
    vascular_disease: bool | None = False,
) -> dict[str, Any]:
    """CHA₂DS₂-VASc stroke risk in atrial fibrillation (0–9).

    Age bands are mutually exclusive (65–74 → 1, ≥75 → 2) and prior stroke/TIA
    scores 2. Female sex is a *modifier*, not a stand-alone reason to
    anticoagulate: on score alone the conventional tiers are 0 in men / 1 in
    women = none, 1 in men / 2 in women = consider, ≥2 in men / ≥3 in women =
    anticoagulation recommended.

    Unknown sex or age leaves the score incomplete rather than silently scoring
    the patient as male or under 65.
    """
    components: dict[str, dict[str, Any]] = {}
    missing: list[str] = []

    for name, flag, points, detail in (
        ("heart_failure", heart_failure, 1, "heart failure / LV systolic dysfunction"),
        ("hypertension", hypertension, 1, "hypertension"),
        ("diabetes", diabetes, 1, "diabetes mellitus"),
        ("stroke_tia", stroke_tia, 2, "prior stroke, TIA or thromboembolism"),
        ("vascular_disease", vascular_disease, 1, "vascular disease (prior MI, PAD or aortic plaque)"),
    ):
        components[name] = {"points": points if flag else 0, "detail": detail if flag else f"no {detail}"}

    if age is None:
        missing.append("age")
    else:
        if age >= 75:
            components["age"] = {"points": 2, "detail": f"{age} years (≥75)"}
        elif age >= 65:
            components["age"] = {"points": 1, "detail": f"{age} years (65–74)"}
        else:
            components["age"] = {"points": 0, "detail": f"{age} years (<65)"}

    sex_key = (sex or "").strip().lower()
    if sex_key in ("female", "f", "woman"):
        components["sex"] = {"points": 1, "detail": "female"}
    elif sex_key in ("male", "m", "man"):
        components["sex"] = {"points": 0, "detail": "male"}
    else:
        missing.append("sex")

    known_points = sum(item["points"] for item in components.values())
    complete = not missing
    score = known_points if complete else None
    tier = None
    if complete:
        female = components["sex"]["points"] == 1
        threshold_recommended = 3 if female else 2
        threshold_consider = 2 if female else 1
        if score >= threshold_recommended:
            tier = "recommended"
        elif score >= threshold_consider:
            tier = "consider"
        else:
            tier = "none"

    return {
        "name": "CHA2DS2-VASc",
        "score": score,
        "known_points": known_points,
        "max_score": 9,
        "complete": complete,
        "annual_stroke_risk_pct": CHA2DS2_VASC_STROKE_RISK.get(score) if complete else None,
        "anticoagulation_tier": tier,
        "components": components,
        "missing": missing,
        "source": CHA2DS2_VASC_SOURCE,
        "note": (
            "Female sex is a modifier: the tiers are 0 (men) / 1 (women) none, "
            "1 / 2 consider, >=2 / >=3 recommended - the decision stays clinical."
        ),
    }


# ---------------------------------------------------------------------------
# ASCVD (2013 ACC/AHA Pooled Cohort Equations, 10-year risk)
# ---------------------------------------------------------------------------

# Four models, one per sex and race/ethnicity group, over the same thirteen
# terms. A term the published table leaves out of a model has coefficient zero.
ASCVD_TERMS = (
    "ln_age", "ln_age_squared", "ln_total_cholesterol", "ln_age_x_ln_total_cholesterol",
    "ln_hdl", "ln_age_x_ln_hdl", "ln_treated_sbp", "ln_age_x_ln_treated_sbp",
    "ln_untreated_sbp", "ln_age_x_ln_untreated_sbp", "current_smoker", "ln_age_x_smoker", "diabetes",
)

# Risk is 1 - S10^exp(sum(beta * x) - mean). The guideline publishes a single
# centering value per group, not a mean per term, so that is what is stored.
ASCVD_GROUPS: dict[str, dict[str, Any]] = {
    "white_men": {
        "label": "white men",
        "mean": 61.1816,
        "baseline_survival": 0.91436,
        "betas": (12.344, 0.0, 11.853, -2.664, -7.990, 1.769, 1.797, 0.0, 1.764, 0.0, 7.837, -1.795, 0.658),
    },
    "white_women": {
        "label": "white women",
        "mean": -29.1817,
        "baseline_survival": 0.96652,
        "betas": (-29.799, 4.884, 13.540, -3.114, -13.578, 3.149, 2.019, 0.0, 1.957, 0.0, 7.574, -1.665, 0.661),
    },
    "aa_men": {
        "label": "African American men",
        "mean": 19.5425,
        "baseline_survival": 0.89536,
        "betas": (2.469, 0.0, 0.302, 0.0, -0.307, 0.0, 1.916, 0.0, 1.809, 0.0, 0.549, 0.0, 0.645),
    },
    "aa_women": {
        "label": "African American women",
        "mean": 86.6081,
        "baseline_survival": 0.95334,
        "betas": (17.1141, 0.0, 0.9396, 0.0, -18.9196, 4.4748, 29.2907, -6.4321, 27.8197, -6.0873, 0.6908, 0.0, 0.8738),
    },
}

ASCVD_SEX_GROUPS: dict[str, tuple[str, str]] = {
    "male": ("white_men", "aa_men"),
    "female": ("white_women", "aa_women"),
}
ASCVD_RACE_GROUPS: dict[str, dict[str, str]] = {
    "white": {"male": "white_men", "female": "white_women"},
    "african_american": {"male": "aa_men", "female": "aa_women"},
}

# The ranges the equations were derived and validated over. Outside them the
# arithmetic still runs, but the reading is flagged rather than trusted.
ASCVD_VALID_RANGES: dict[str, tuple[float, float]] = {
    "age": (40, 79),
    "total_cholesterol_mg_dl": (130, 320),
    "hdl_mg_dl": (20, 100),
    "systolic_bp": (90, 200),
}

# Clinical 10-year risk categories (ACC/AHA). Banded on the reported value, so
# the category always agrees with the number on screen. The published categories
# are <5 low, 5 to <7.5 borderline, 7.5 to <20 intermediate, >=20 high — that is,
# each upper bound is EXCLUSIVE, unlike the point scores' bands: 5.0% is
# borderline and 20.0% is high. ``_band_from_cutoffs`` treats its bounds as
# inclusive, which would put both of those a band too low, so the comparison is
# spelled out here.
_ASCVD_CATEGORY_CUTOFFS = ((5.0, "low"), (7.5, "borderline"), (20.0, "intermediate"), (float("inf"), "high"))
ASCVD_REPORTING_PRECISION = 1
ASCVD_STATIN_THRESHOLD = 7.5  # intermediate and above: a statin is indicated

ASCVD_GROUP_LABELS = {key: spec["label"] for key, spec in ASCVD_GROUPS.items()}

ASCVD_SOURCE = (
    "2013 ACC/AHA Pooled Cohort Equations (Goff et al., Circulation 2014) — 10-year risk of a "
    "first atherosclerotic cardiovascular event; coefficients, group centering value and "
    "baseline survival as implemented by the reference PooledCohort R package."
)

_ASCVD_TERM_LABELS = {
    "ln_age": "ln(age)",
    "ln_age_squared": "ln(age) squared",
    "ln_total_cholesterol": "ln(total cholesterol)",
    "ln_age_x_ln_total_cholesterol": "ln(age) x ln(total cholesterol)",
    "ln_hdl": "ln(HDL)",
    "ln_age_x_ln_hdl": "ln(age) x ln(HDL)",
    "ln_treated_sbp": "ln(systolic BP), treated",
    "ln_age_x_ln_treated_sbp": "ln(age) x ln(systolic BP), treated",
    "ln_untreated_sbp": "ln(systolic BP), untreated",
    "ln_age_x_ln_untreated_sbp": "ln(age) x ln(systolic BP), untreated",
    "current_smoker": "current smoker",
    "ln_age_x_smoker": "ln(age) x current smoker",
    "diabetes": "diabetes",
}


def _ascvd_term_values(
    *,
    age: int,
    total_cholesterol_mg_dl: float,
    hdl_mg_dl: float,
    systolic_bp: float,
    treated_for_hypertension: bool,
    current_smoker: bool,
    diabetes: bool,
) -> dict[str, float]:
    """The thirteen transformed terms, with the unused SBP half left at zero."""
    ln_age = math.log(age)
    ln_total = math.log(total_cholesterol_mg_dl)
    ln_hdl = math.log(hdl_mg_dl)
    ln_sbp = math.log(systolic_bp)
    values = {term: 0.0 for term in ASCVD_TERMS}
    values["ln_age"] = ln_age
    values["ln_age_squared"] = ln_age ** 2
    values["ln_total_cholesterol"] = ln_total
    values["ln_age_x_ln_total_cholesterol"] = ln_age * ln_total
    values["ln_hdl"] = ln_hdl
    values["ln_age_x_ln_hdl"] = ln_age * ln_hdl
    if treated_for_hypertension:
        values["ln_treated_sbp"] = ln_sbp
        values["ln_age_x_ln_treated_sbp"] = ln_age * ln_sbp
    else:
        values["ln_untreated_sbp"] = ln_sbp
        values["ln_age_x_ln_untreated_sbp"] = ln_age * ln_sbp
    if current_smoker:
        values["current_smoker"] = 1.0
        values["ln_age_x_smoker"] = ln_age
    if diabetes:
        values["diabetes"] = 1.0
    return values


def _ascvd_linear_predictor(group: str, values: dict[str, float]) -> float:
    """sum(beta * x) for one group — the published linear predictor, before centering."""
    return sum(beta * values[term] for term, beta in zip(ASCVD_TERMS, ASCVD_GROUPS[group]["betas"]))


def _ascvd_risk(group: str, values: dict[str, float]) -> float:
    """Unrounded 10-year risk in percent for one group's equation."""
    spec = ASCVD_GROUPS[group]
    return 100.0 * (1.0 - spec["baseline_survival"] ** math.exp(_ascvd_linear_predictor(group, values) - spec["mean"]))


def _ascvd_category(risk_pct: float) -> str:
    for limit, label in _ASCVD_CATEGORY_CUTOFFS:
        if risk_pct < limit:
            return label
    return _ASCVD_CATEGORY_CUTOFFS[-1][1]


def _ascvd_components(group: str, values: dict[str, float], *, age, total_cholesterol_mg_dl, hdl_mg_dl,
                      systolic_bp, treated_for_hypertension, current_smoker, diabetes) -> dict[str, dict[str, Any]]:
    """Every term's contribution, so the sum can be checked by hand."""
    details = {
        "ln_age": f"ln({age}) = {values['ln_age']:.4f}",
        "ln_age_squared": f"ln({age}) squared = {values['ln_age_squared']:.4f}",
        "ln_total_cholesterol": f"ln({total_cholesterol_mg_dl:g} mg/dL) = {values['ln_total_cholesterol']:.4f}",
        "ln_age_x_ln_total_cholesterol": f"{values['ln_age']:.4f} x {values['ln_total_cholesterol']:.4f}",
        "ln_hdl": f"ln({hdl_mg_dl:g} mg/dL) = {values['ln_hdl']:.4f}",
        "ln_age_x_ln_hdl": f"{values['ln_age']:.4f} x {values['ln_hdl']:.4f}",
        "ln_treated_sbp": f"on treatment, ln({systolic_bp:g} mmHg) = {values['ln_treated_sbp']:.4f}",
        "ln_age_x_ln_treated_sbp": f"{values['ln_age']:.4f} x {values['ln_treated_sbp']:.4f}",
        "ln_untreated_sbp": f"not on treatment, ln({systolic_bp:g} mmHg) = {values['ln_untreated_sbp']:.4f}",
        "ln_age_x_ln_untreated_sbp": f"{values['ln_age']:.4f} x {values['ln_untreated_sbp']:.4f}",
        "current_smoker": "current smoker" if current_smoker else "not a current smoker",
        "ln_age_x_smoker": f"ln({age}) = {values['ln_age_x_smoker']:.4f}" if current_smoker else "not a current smoker",
        "diabetes": "diabetes" if diabetes else "no diabetes",
    }
    # The SBP half that does not apply is not shown at all, and neither is a term
    # this group's model does not use — the components are the sum as published.
    untaken = (
        ("ln_untreated_sbp", "ln_age_x_ln_untreated_sbp") if treated_for_hypertension
        else ("ln_treated_sbp", "ln_age_x_ln_treated_sbp")
    )
    betas = dict(zip(ASCVD_TERMS, ASCVD_GROUPS[group]["betas"]))
    components: dict[str, dict[str, Any]] = {}
    for term in ASCVD_TERMS:
        beta = betas[term]
        value = values[term]
        if beta == 0.0 or term in untaken:
            continue
        components[_ASCVD_TERM_LABELS[term]] = {
            "coefficient": beta,
            "value": round(value, 4),
            "contribution": round(beta * value, 4),
            "detail": details[term],
        }
    return components


def ascvd_score(
    *,
    age: int | None,
    sex: str | None,
    race: str | None,
    total_cholesterol_mg_dl: float | None,
    hdl_mg_dl: float | None,
    systolic_bp: float | None,
    treated_for_hypertension: bool | None,
    current_smoker: bool | None,
    diabetes: bool | None,
) -> dict[str, Any]:
    """Ten-year ASCVD risk (percent) from the 2013 ACC/AHA Pooled Cohort Equations.

    This is the *primary* prevention instrument: it estimates the risk of a
    first atherosclerotic event and is reported even for a patient who already
    has disease, but it is only a treatment-threshold reading — HEART and GRACE
    are what grade an acute presentation.

    ``race`` is ``"white"`` or ``"african_american"``, because the guideline
    publishes a separate equation for each. Two conventions, stated plainly
    because they are choices of this implementation and not of the guideline:

    - **No race captured means the higher of the two sex-matched equations is
      reported**, with the other one returned beside it in ``alternative``. A
      default to one group would quietly under-estimate half the patients; the
      conservative read at least errs towards treating.
    - **Inputs outside the validated ranges are reported, not hidden.**
      ``out_of_range`` names them and ``in_range`` is false; a caller deciding
      on treatment should require ``in_range``.

    ``score`` is ``None`` whenever an input is missing — including an explicitly
    unknown smoking or diabetes status, which is not the same as "no".
    """
    labels = {
        "age": "age",
        "sex": "sex",
        "total_cholesterol_mg_dl": "total cholesterol",
        "hdl_mg_dl": "HDL cholesterol",
        "systolic_bp": "systolic blood pressure",
        "treated_for_hypertension": "hypertension treatment status",
        "current_smoker": "smoking status",
        "diabetes": "diabetes status",
    }
    given = {
        "age": age,
        "sex": sex,
        "total_cholesterol_mg_dl": total_cholesterol_mg_dl,
        "hdl_mg_dl": hdl_mg_dl,
        "systolic_bp": systolic_bp,
        "treated_for_hypertension": treated_for_hypertension,
        "current_smoker": current_smoker,
        "diabetes": diabetes,
    }
    missing = [labels[name] for name, value in given.items() if value is None]

    sex_key = (sex or "").strip().lower()
    candidates: tuple[str, ...] = ()
    if sex_key in ASCVD_SEX_GROUPS:
        race_key = (race or "").strip().lower()
        single = ASCVD_RACE_GROUPS.get(race_key, {}).get(sex_key)
        candidates = (single,) if single else ASCVD_SEX_GROUPS[sex_key]

    out_of_range = [
        f"{name.replace('_mg_dl', '').replace('_', ' ')} {value:g}" if isinstance(value, (int, float)) else name
        for name, (low, high) in ASCVD_VALID_RANGES.items()
        for value in [given.get(name)]
        if isinstance(value, (int, float)) and not low <= value <= high
    ]

    reading: dict[str, Any] | None = None
    components: dict[str, dict[str, Any]] = {}
    if not missing:
        values = _ascvd_term_values(
            age=int(age),
            total_cholesterol_mg_dl=float(total_cholesterol_mg_dl),
            hdl_mg_dl=float(hdl_mg_dl),
            systolic_bp=float(systolic_bp),
            treated_for_hypertension=bool(treated_for_hypertension),
            current_smoker=bool(current_smoker),
            diabetes=bool(diabetes),
        )
        risks = [(group, _ascvd_risk(group, values)) for group in candidates]
        chosen_group, chosen_risk = max(risks, key=lambda item: item[1])
        others = [
            {"group": ASCVD_GROUPS[group]["label"], "risk_pct": round(risk, ASCVD_REPORTING_PRECISION)}
            for group, risk in risks if group != chosen_group
        ]
        components = _ascvd_components(
            chosen_group, values,
            age=age, total_cholesterol_mg_dl=total_cholesterol_mg_dl, hdl_mg_dl=hdl_mg_dl,
            systolic_bp=systolic_bp, treated_for_hypertension=treated_for_hypertension,
            current_smoker=current_smoker, diabetes=diabetes,
        )
        spec = ASCVD_GROUPS[chosen_group]
        reading = {
            "group": spec["label"],
            "race_captured": len(candidates) == 1,
            "alternative": others[0] if others else None,
            "risk_pct": round(chosen_risk, ASCVD_REPORTING_PRECISION),
            "linear_predictor": {
                "sum": round(_ascvd_linear_predictor(chosen_group, values), 4),
                "mean": spec["mean"],
                "baseline_survival": spec["baseline_survival"],
            },
        }

    complete = not missing
    risk_pct = reading["risk_pct"] if reading else None

    if not complete:
        note = "Risk requires every input: " + ", ".join(missing) + "."
    elif out_of_range:
        note = (
            "Outside the range the equations were derived over "
            f"({', '.join(out_of_range)}); reported with that caveat, not as a validated estimate."
        )
    elif not reading["race_captured"]:
        note = (
            "Race/ethnicity was not captured, so the higher of the two sex-matched equations is "
            f"shown and the other is reported as {reading['alternative']['group']} "
            f"({reading['alternative']['risk_pct']}%)."
        )
    else:
        note = "Risk category is the conventional ACC/AHA reading of the reported value."

    return {
        "name": "ASCVD-PCE",
        "score": risk_pct,
        "risk_pct": risk_pct,
        "complete": complete,
        "category": _ascvd_category(risk_pct) if risk_pct is not None else None,
        "statin_indicated": bool(risk_pct is not None and risk_pct >= ASCVD_STATIN_THRESHOLD),
        "group": reading["group"] if reading else None,
        "race_captured": reading["race_captured"] if reading else None,
        "alternative": reading["alternative"] if reading else None,
        "linear_predictor": reading["linear_predictor"] if reading else None,
        "in_range": not out_of_range,
        "out_of_range": out_of_range,
        "components": components,
        "missing": missing,
        "source": ASCVD_SOURCE,
        "applies_to": "primary prevention (10-year risk of a first ASCVD event)",
        "note": note,
    }
