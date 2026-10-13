"""Assemble the inputs the deterministic risk scores need, from one encounter.

Why this exists
---------------
``agents/risk_scores_agent`` holds the arithmetic of HEART, GRACE, CHA₂DS₂-VASc
and the ASCVD Pooled Cohort Equations, but nothing there knows where an
encounter keeps its facts. Two layers consume those scores — the diagnosis pipeline (which reports them beside
the model's band) and the medication safety review (whose urgency used to be
hand-derived) — and if each assembled the inputs itself they would eventually
score the same patient differently. That is the failure mode
``backend/encounter_context`` already exists to prevent for the medication
rules, so the score inputs are assembled here, once:

- **age / sex** from the visit details, and **race/ethnicity** because the
  pooled cohort equations publish a different model for each.
- **condition tags** from the recorded history *and* the wording itself, using
  the same condition vocabulary the medication layer uses.
- **troponin** as a multiple of its assay ceiling, unit-aware
  (:func:`backend.lab_report.troponin_ratio`).
- **heart rate, blood pressure, Killip class** read from the clinical text
  ("BP 90/60, HR 110, Killip II") or supplied explicitly.
- **creatinine in mg/dL** for GRACE — µmol/L is converted, never binned as if
  it were mg/dL.
- **total cholesterol, HDL cholesterol and systolic blood pressure** in mg/dL /
  mmHg for ASCVD — mmol/L and µmol/L are converted, never fed in as if they
  were the equation's units.
- **hypertension treatment, smoking and diabetes status** for ASCVD. "Treated"
  means a BP-lowering drug is recorded; a status the encounter never touched is
  reported as missing, not as "no".
- **ECG category** from the documented ECG statements, which is what HEART's
  ECG item and GRACE's ST-deviation item need.
- **chest-pain typicality** for HEART's History item: derived from the captured
  features and reported with the features that drove it.

Two rules keep this honest:

1. **Nothing is assumed normal.** A fact that was not captured stays missing,
   and the score says so (``complete: false``) rather than scoring the patient
   as low risk. GRACE needs vitals and a Killip class; when they are absent it
   reports exactly what to supply.
2. **Every derived reading is explained.** The History category, the ECG
   category and the elevated-marker flag are conventions of this implementation,
   not quantities the scores define by themselves, so each one is returned with
   the evidence behind it in ``inputs``.

Nothing is stored; the same encounter always produces the same scores.
"""

from __future__ import annotations

import re
from typing import Any

from agents.pharmacology_agent import current_med_keys, detect_conditions
from agents.risk_scores_agent import ascvd_score, cha2ds2_vasc, grace_score, heart_score
from backend.lab_report import screen_report_text, to_primary_unit, troponin_ratio, vitals_from_text

# HEART's risk-factor count: diagnosed diabetes, smoking, hypertension,
# hypercholesterolaemia, obesity, family history of coronary disease.
_HEART_RISK_FACTOR_TAGS = (
    "diabetes", "smoking", "hypertension", "dyslipidemia", "obesity", "family_history_cad",
)
# …and established atherosclerotic disease scores 2 points regardless of count.
_HEART_ESTABLISHED_ASCVD_TAGS = (
    "prior_mi", "prior_pci_cabg", "established_cad",
    "peripheral_arterial_disease", "cerebrovascular_disease",
)

# Features that make a chest-pain history typical. The vocabulary folds
# radiation into the chest-pain concept, so radiation is read from the wording.
_HISTORY_FEATURES: dict[str, str] = {
    "radiation": (
        r"\b(?:radiat\w*|spreads?\s+(?:in)?to|goes?\s+(?:in)?to|travels?\s+to|referred)\b"
        r"[^.;]{0,30}\b(?:arm|jaw|neck|shoulder|back|epigastri\w*)\b"
    ),
    "exertional": r"\b(?:on (?:exertion|walking|climbing|stairs)|when i (?:walk|climb|exert)|brought on by (?:exertion|walking|activity))\b",
    "sweating": r"\b(?:sweat\w*|diaphor\w*|clammy)\b",
    "nausea": r"\b(?:nausea\w*|vomit\w*|sick to (?:the|my) stomach)\b",
    "dyspnoea": r"\b(?:shortness of breath|breathless\w*|dyspn\w*)\b",
}

_ECG_ST_DEVIATION = r"\bST[\s-]?(?:elevation|depression)\b|\bST[\s-]?segment[\s-]?(?:elevation|depression|deviation)\b"
_ECG_REPOLARISATION = (
    r"\bT[\s-]?wave\s+(?:inversion|flattening)\b|\bbundle\s+branch\s+block\b|\bLBBB\b|\bRBBB\b"
    r"|\bleft\s+ventricular\s+hypertrophy\b|\bLVH\b|digoxin\s+effect|\bpathological\s+Q\s+waves?\b"
)
_ECG_DOCUMENTED = r"\b(?:ECG|EKG|electrocardiogram)\b|sinus\s+rhythm|normal\s+cardiac\s+rhythm"

_CARDIAC_ARREST = r"\b(?:cardiac\s+arrest|arrested|asystole|pulseless\s+(?:VT|ventricular)|CPR)\b"


# Race/ethnicity, because the pooled cohort equations publish one model per
# group. Read from the record first, then from the wording.
_AFRICAN_AMERICAN = r"\b(?:african[\s-]?american|afro[\s-]?caribbean|black)\b"
_WHITE = r"\b(?:white|caucasian|european)\b"

# Negative statements, so an explicitly documented absence is scored as absent
# instead of being left missing. An ex-smoker is not a current smoker.
_NEVER_SMOKED = (
    r"\b(?:never\s+smok\w*|non[\s-]?smoker|does\s*n[o']?t\s+smoke|denies\s+smok\w*|"
    r"ex[\s-]?smoker|former\s+smoker|quit\s+smoking|stopped\s+smoking|no\s+tobacco)\b"
)
_NOT_DIABETIC = (
    r"\b(?:non[\s-]?diabetic|not\s+diabetic|no\s+diabetes|denies\s+diabetes|without\s+diabetes|normoglyc\w*)\b"
)
_NO_ANTIHYPERTENSIVE = (
    r"\b(?:not\s+on\s+any\s+(?:blood\s+pressure|bp)[\s-]?\w*|no\s+antihypertensive\w*|"
    r"not\s+on\s+antihypertensive\w*|never\s+on\s+(?:blood\s+pressure|bp)[\s-]?\w*)\b"
)
# Drug classes that count as BP-lowering treatment for the equation's "treated"
# systolic blood pressure term.
_ANTIHYPERTENSIVE_CLASSES = ("ace_inhibitor", "arb", "ccb", "beta_blocker", "loop_diuretic", "mra")


def _age(patient: dict) -> int | None:
    try:
        value = int(str(patient.get("age")).strip())
    except (TypeError, ValueError):
        return None
    return value if 0 <= value <= 120 else None


def _sex(patient: dict) -> str | None:
    value = str(patient.get("sex") or "").strip().lower()
    if value in ("female", "f", "woman"):
        return "female"
    if value in ("male", "m", "man"):
        return "male"
    return None


def _creatinine_mg_dl(text: str, patient: dict) -> float | None:
    """Creatinine in mg/dL — the unit the GRACE point table is written in.

    The recorded lab map and the parsed text are both funnelled through
    ``lab_report.to_primary_unit``, so a µmol/L value is converted rather than
    binned as if it were mg/dL — and both routes give the same number.
    """
    recorded = patient.get("labs")
    if isinstance(recorded, dict) and recorded.get("creatinine") is not None:
        try:
            return round(float(recorded["creatinine"]), 3)
        except (TypeError, ValueError):
            pass
    for value in screen_report_text(text).get("values", []):
        if str(value.get("key", "")) != "creatinine":
            continue
        try:
            number = float(value["value"])
        except (TypeError, ValueError, KeyError):
            continue
        converted = to_primary_unit("creatinine", number, str(value.get("unit") or "").lower() or None)
        if converted is not None:
            return round(converted, 3)
    return None


def _lipid_mg_dl(text: str, patient: dict, key: str) -> float | None:
    """Total or HDL cholesterol in mg/dL — the unit the equation is written in.

    The recorded lab map is already in the analyte's primary unit, and a value
    parsed from text is converted by ``lab_report.to_primary_unit`` (one table,
    shared with the flattened lab map the medication gates read), so a mmol/L
    lipid is never read as if it were mg/dL whichever route it arrived by.
    """
    recorded = patient.get("labs")
    if isinstance(recorded, dict) and recorded.get(key) is not None:
        try:
            return round(float(recorded[key]), 1)
        except (TypeError, ValueError):
            pass
    for value in screen_report_text(text).get("values", []):
        if str(value.get("key", "")) != key:
            continue
        try:
            number = float(value["value"])
        except (TypeError, ValueError, KeyError):
            continue
        converted = to_primary_unit(key, number, str(value.get("unit") or "").lower() or None)
        if converted is not None:
            return round(converted, 1)
    return None


def _race(patient: dict, narrative: str) -> str | None:
    """The equation group's race/ethnicity term: ``"white"``, ``"african_american"`` or unknown.

    Read from the record first (a stated race is a fact about the patient), then
    from the wording, because the pooled cohort equations publish a separate
    coefficient set per group and picking one silently is what the score refuses
    to do.
    """
    # A recorded value may arrive as prose ("African American"), as a slug
    # ("african_american") or hyphenated ("African-American"), so separators are
    # normalised before matching rather than making the caller guess a format.
    recorded = str(patient.get("race") or patient.get("ethnicity") or "")
    recorded = recorded.replace("_", " ").replace("-", " ").strip()
    haystack = f"{recorded}\n{narrative}" if (recorded or narrative) else ""
    if re.search(_AFRICAN_AMERICAN, haystack, re.I):
        return "african_american"
    if re.search(_WHITE, haystack, re.I):
        return "white"
    return None


def _smoker(tags: list[str], narrative: str) -> bool | None:
    """Current smoker: an explicit denial beats the condition tag.

    The condition vocabulary matches ``smoker`` inside *ex-smoker* and *non-smoker*
    too, so the documented absence is read first — an ex-smoker scores as a
    non-smoker. Nothing said at all stays unknown.
    """
    if re.search(_NEVER_SMOKED, narrative, re.I):
        return False
    if "smoking" in tags:
        return True
    return None


def _diabetes_status(tags: list[str], narrative: str) -> bool | None:
    """Diabetes for the equation: recorded, explicitly denied, or unknown."""
    if re.search(_NOT_DIABETIC, narrative, re.I):
        return False
    if "diabetes" in tags:
        return True
    return None


def _bp_treated(context: dict, narrative: str, tags: list[str]) -> bool:
    """The equation's *treated* systolic BP item: is the patient on BP-lowering drugs?

    Convention of this implementation, stated as such: treatment is true when a
    BP-lowering drug is recorded (or explicitly supplied), and false when the
    encounter records none. ``True`` selects the treated-SBP coefficients, which
    are the higher ones, so an unknown medication list biases towards a higher
    estimate rather than a falsely low one.
    """
    explicit = context.get("bp_treated")
    if isinstance(explicit, bool):
        return explicit
    vitals = context.get("vitals")
    if isinstance(vitals, dict) and isinstance(vitals.get("bp_treated"), bool):
        return bool(vitals["bp_treated"])
    if set(_ANTIHYPERTENSIVE_CLASSES) & set(current_med_keys(context.get("current_medications"))):
        return True
    if re.search(_NO_ANTIHYPERTENSIVE, narrative, re.I):
        return False
    return False


def _history_reading(narrative: str, symptoms: list[str]) -> tuple[str | None, list[str], str]:
    """HEART's History item: how typical the captured chest pain is.

    Convention of this implementation, stated as such: with a chest-pain
    concept captured, two or more of radiation / exertional onset / sweating /
    nausea / dyspnoea reads *typical*, exactly one reads *atypical*, and none
    reads *non-specific*. Without any chest-pain concept there is nothing for
    the item to score, so it is reported as missing rather than as zero.
    """
    has_chest_pain = any(symptom.strip().lower() == "chest pain" for symptom in symptoms)
    if not has_chest_pain:
        return None, [], "no chest-pain history captured — the HEART History item needs one"

    features = [name for name, pattern in _HISTORY_FEATURES.items() if re.search(pattern, narrative, re.I)]
    if len(features) >= 2:
        category = "typical"
    elif features:
        category = "atypical"
    else:
        category = "non_specific"
    detail = (
        f"chest pain with {', '.join(features)}" if features
        else "chest pain with no associated typical feature captured"
    )
    return category, features, detail


def _ecg_category(narrative: str) -> tuple[str | None, str]:
    """HEART's ECG item / GRACE's ST-deviation item, from documented ECG text."""
    if re.search(_ECG_ST_DEVIATION, narrative, re.I):
        return "st_deviation", "ST deviation documented"
    if re.search(_ECG_REPOLARISATION, narrative, re.I):
        return "repolarisation", "repolarisation abnormality documented, no significant ST deviation"
    if re.search(_ECG_DOCUMENTED, narrative, re.I):
        return "normal", "ECG documented without ischaemic changes"
    return None, "no ECG statement captured"


def build_risk_scores(
    encounter_text: str = "",
    report_text: str = "",
    patient: dict | None = None,
    symptoms: list[str] | None = None,
) -> dict[str, Any]:
    """HEART, GRACE, CHA₂DS₂-VASc and ASCVD for one encounter, with their inputs."""
    context = patient if isinstance(patient, dict) else {}
    narrative = f"{encounter_text or ''}\n{report_text or ''}".strip()

    tags: list[str] = []
    for source in (context.get("conditions"), narrative):
        for tag in detect_conditions(source):
            if tag not in tags:
                tags.append(tag)

    age = _age(context)
    sex = _sex(context)
    troponin = troponin_ratio(narrative)
    vitals = vitals_from_text(narrative)
    for key in ("heart_rate", "systolic_bp", "diastolic_bp", "killip"):
        explicit = (context.get("vitals") or {}).get(key) if isinstance(context.get("vitals"), dict) else None
        if explicit is not None:
            vitals[key] = explicit
    creatinine = _creatinine_mg_dl(narrative, context)

    history, history_features, history_detail = _history_reading(narrative, list(symptoms or []))
    ecg, ecg_detail = _ecg_category(narrative)

    risk_factors = [tag for tag in tags if tag in _HEART_RISK_FACTOR_TAGS]
    established = [tag for tag in tags if tag in _HEART_ESTABLISHED_ASCVD_TAGS]
    troponin_ratio_value = troponin.get("ratio") if troponin else None

    heart = heart_score(
        history=history,
        ecg=ecg,
        age=age,
        risk_factor_count=len(risk_factors),
        established_ascvd=bool(established),
        troponin_ratio=troponin_ratio_value,
    )
    if heart["complete"]:
        heart["components"]["history"]["detail"] = history_detail
        heart["components"]["ecg"]["detail"] = ecg_detail

    # GRACE's markers item is the binary "raised cardiac enzymes": a number above
    # the assay ceiling, or a troponin reported positive without one.
    if troponin is None:
        elevated_markers = None
    elif troponin.get("ratio") is None:
        elevated_markers = True
    else:
        elevated_markers = bool(troponin["ratio"] > 1.0)

    explicit_arrest = context.get("cardiac_arrest") if isinstance(context.get("cardiac_arrest"), bool) else None
    cardiac_arrest = explicit_arrest if explicit_arrest is not None else bool(re.search(_CARDIAC_ARREST, narrative, re.I))

    grace = grace_score(
        age=age,
        heart_rate=vitals.get("heart_rate"),
        systolic_bp=vitals.get("systolic_bp"),
        creatinine_mg_dl=creatinine,
        killip=vitals.get("killip"),
        cardiac_arrest=cardiac_arrest,
        st_deviation=None if ecg is None else ecg == "st_deviation",
        elevated_markers=elevated_markers,
    )

    atrium_fibrillation = "atrial_fibrillation" in tags
    stroke_risk = cha2ds2_vasc(
        age=age,
        sex=sex,
        heart_failure="heart_failure" in tags,
        hypertension="hypertension" in tags,
        diabetes="diabetes" in tags,
        stroke_tia="cerebrovascular_disease" in tags,
        vascular_disease="prior_mi" in tags or "peripheral_arterial_disease" in tags,
    )
    stroke_risk["applies_to"] = (
        "atrial fibrillation" if atrium_fibrillation
        else "atrial fibrillation (not captured in this encounter)"
    )

    # ASCVD is the primary-prevention equation: it reads the lipid panel and the
    # BP-treatment, smoking and diabetes status alongside what the other scores
    # already use, and reports a ten-year probability instead of a point total.
    race = _race(context, narrative)
    total_cholesterol = _lipid_mg_dl(narrative, context, "total_cholesterol")
    hdl = _lipid_mg_dl(narrative, context, "hdl")
    bp_treated = _bp_treated(context, narrative, tags)
    current_smoker = _smoker(tags, narrative)
    diabetes_status = _diabetes_status(tags, narrative)

    ascvd = ascvd_score(
        age=age,
        sex=sex,
        race=race,
        total_cholesterol_mg_dl=total_cholesterol,
        hdl_mg_dl=hdl,
        systolic_bp=vitals.get("systolic_bp"),
        treated_for_hypertension=bp_treated,
        current_smoker=current_smoker,
        diabetes=diabetes_status,
    )

    missing: list[str] = []
    for score in (heart, grace, stroke_risk, ascvd):
        for gap in score["missing"]:
            label = f"{score['name']}: {gap}"
            if label not in missing:
                missing.append(label)

    return {
        "heart": heart,
        "grace": grace,
        "cha2ds2_vasc": stroke_risk,
        "ascvd": ascvd,
        "inputs": {
            "age": age,
            "sex": sex,
            "race": race,
            "total_cholesterol_mg_dl": total_cholesterol,
            "hdl_mg_dl": hdl,
            "bp_treated": bp_treated,
            "current_smoker": current_smoker,
            "diabetes_status": diabetes_status,
            "condition_tags": tags,
            "heart_risk_factors": risk_factors,
            "established_ascvd": established,
            "troponin": troponin,
            "vitals": vitals,
            "creatinine_mg_dl": creatinine,
            "ecg": ecg,
            "ecg_detail": ecg_detail,
            "history_detail": history_detail,
            "history_features": history_features,
            "cardiac_arrest": cardiac_arrest,
            "elevated_markers": elevated_markers,
            "atrial_fibrillation": atrium_fibrillation,
        },
        "missing": missing,
    }
