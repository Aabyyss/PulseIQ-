"""Deterministic cardiac risk scores: HEART, GRACE and CHA₂DS₂-VASc.

Why this module exists
----------------------
Until now the urgency of an encounter was hand-derived inside the medication
layer ("chest pain is present, so call it an emergency") and the diagnosis layer
reported a model probability band. Both are defensible, but neither is a
*score*: a clinician cannot check the reasoning against a published instrument,
and two layers can disagree about the same patient.

These three scores are pure arithmetic over captured facts — no model, no LLM,
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
  patient whose presentation already suggests one; they do not diagnose.

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
"""

from __future__ import annotations

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
    band = _band_from_cutoffs(score, [(3, "low"), (6, "intermediate"), (10, "high")]) if complete else None

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
        band = "low" if score < 109 else ("intermediate" if score <= 140 else "high")
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
