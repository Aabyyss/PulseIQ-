"""Medication recommendation & safety review — an 18th rule-grounded module.

Why this exists
---------------
The screening pipeline answers "how urgent is this presentation?". It does not
answer the next question a clinician asks: *which drugs are reasonable for
this patient, and which are unsafe?* This agent closes that gap in the same
style as every other agent in PulseIQ — deterministic rules over a curated
table, no network, no LLM, nothing invented. Every entry names the captured
fact that triggered it, so a clinician can overrule it on the record.

What it weighs
--------------
- presentation: symptom concepts + the screening risk band
- conditions / history: CAD, prior MI, prior PCI/CABG, heart failure, atrial
  fibrillation, hypertension, diabetes, CKD, asthma/COPD, ulcer or bleeding,
  stroke/TIA, pregnancy, bradyarrhythmia, dyslipidaemia, smoking
- allergies: drug *and* drug-class allergies (aspirin/NSAID, statin, ACE
  inhibitor/ARB, sulfonamide, nitrate, ...), mapped onto the options offered
- current medications: aliases and common brand names — used for interaction
  screening and for "already documented — verify, don't restart"
- labs: eGFR, creatinine, potassium, sodium, haemoglobin, platelets, LDL,
  troponin, INR, LVEF. Missing labs are reported, never assumed.

Output
------
``recommendations`` (options with priority, dose note, monitoring and the
guideline behind each), ``contraindicated`` (blocked, why, and what triggered
it), ``allergy_alerts``, ``interaction_alerts``, ``monitoring_plan``,
``missing_information`` and ``pathway`` (emergency / urgent / routine).

Decision support only: the clinician selects, prescribes and documents.
"""

from __future__ import annotations

import re
from typing import Any

DISCLAIMER = (
    "Decision support only — these are options for a qualified clinician to "
    "review against the full history, examination and local formulary. "
    "Nothing here is a prescription, and no dose is adjusted automatically."
)


# ---------------------------------------------------------------------------
# Input normalisation
# ---------------------------------------------------------------------------

def as_list(value: Any) -> list[str]:
    """Accept a comma/semicolon/and-separated string, a list of strings, or a
    list of entity dicts (``{"name": "aspirin"}``) and return clean strings."""
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[,;/\n]|\band\b|\bplus\b", value, flags=re.I)
        return [p.strip() for p in parts if p.strip()]
    if isinstance(value, dict):
        value = [value]
    out: list[str] = []
    for item in value:
        if isinstance(item, dict):
            name = item.get("name") or item.get("term") or item.get("drug") or ""
            if str(name).strip():
                out.append(str(name).strip())
        elif str(item).strip():
            out.append(str(item).strip())
    return out


def _has(text: str, *terms: str) -> bool:
    for term in terms:
        if re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", text):
            return True
    return False


def _joined(items: list[str]) -> str:
    return " ; " + " ; ".join(items).lower() + " ; "


_ALLERGY_PHRASE = re.compile(
    r"allerg(?:y|ic|ies)\s*(?:to|:)?\s*([a-z0-9][a-z0-9 ,\-+/]{1,60})",
    re.I,
)


def extract_allergy_mentions(text: str) -> list[str]:
    """Allergy statements in a narrative — "allergic to aspirin and sulfa".

    Only explicit allergy wording matches, so "no known drug allergies"
    yields nothing (the pattern needs a substance after the keyword).
    """
    found: list[str] = []
    for match in _ALLERGY_PHRASE.finditer(str(text or "")):
        chunk = re.split(r"\b(?:but|however|though|no other|nkda)\b|[.;\n]", match.group(1), flags=re.I)[0]
        for term in as_list(chunk):
            if len(term) > 1 and term not in found:
                found.append(term)
        if len(found) >= 8:
            break
    return found


# ---------------------------------------------------------------------------
# Condition / history vocabulary (canonical tags)
# ---------------------------------------------------------------------------

CONDITION_PATTERNS: list[tuple[str, str]] = [
    ("prior_mi", r"\b(?:previous|prior|old|history of)\s+(?:heart attack|myocardial infarction)|post[-\s]?mi\b|\bheart attack\b|\bmyocardial infarction\b"),
    ("prior_pci_cabg", r"\b(?:pci|angioplasty|stent(?:ed|ing)?|cabg|bypass surgery|coronary bypass)\b"),
    ("established_cad", r"\b(?:cad|coronary artery disease|stable angina|angina|ischaemic heart disease|ischemic heart disease|ihd)\b"),
    ("heart_failure", r"\b(?:heart failure|hfref|hfpef|cardiomyopathy|systolic dysfunction|diastolic dysfunction|pulmonary oedema|pulmonary edema)\b"),
    ("atrial_fibrillation", r"\b(?:atrial fibrillation|\baf\b|\bafi\b|irregular heartbeat)\b"),
    ("hypertension", r"\b(?:hypertension|high blood pressure|high bp|raised bp|htn)\b"),
    ("diabetes", r"\b(?:diabet(?:es|ic)|\bt1dm\b|\bt2dm\b|high sugar|sugar problem)\b"),
    ("chronic_kidney_disease", r"\b(?:ckd|chronic kidney disease|renal impairment|renal insufficiency|renal failure|nephropathy)\b"),
    ("obstructive_airway_disease", r"\b(?:asthma|copd|chronic obstructive|emphysema|reactive airway)\b"),
    ("peptic_ulcer", r"\b(?:peptic ulcer|gastric ulcer|duodenal ulcer|gi bleed|gastrointestinal bleed|melena|malaena|haematemesis|hematemesis)\b"),
    ("bleeding_risk", r"\b(?:bleeding disorder|thrombocytopenia|low platelets|bleeding tendency|coagulopathy|haemophilia|hemophilia)\b"),
    ("cerebrovascular_disease", r"\b(?:stroke|\btia\b|transient ischaemic attack|transient ischemic attack|\bcva\b)\b"),
    ("pregnancy", r"\b(?:pregnan(?:t|cy)|gravid|expecting|breastfeeding|breast-feeding|lactating)\b"),
    ("bradyarrhythmia", r"\b(?:bradycardia|heart block|\bav block\b|sick sinus|slow heart rate|pacemaker)\b"),
    ("aortic_stenosis", r"\b(?:aortic stenosis|valvular stenosis|valve stenosis)\b"),
    ("dyslipidemia", r"\b(?:dyslipidemia|dyslipidaemia|hyperlipidemia|hyperlipidaemia|high cholesterol|raised cholesterol)\b"),
    ("gout", r"\bgout\b"),
    ("liver_disease", r"\b(?:cirrhosis|liver disease|hepatic impairment|hepatitis)\b"),
    ("migraine_aura", r"\bmigraine\b"),
    ("smoking", r"\b(?:smok(?:e|es|ing|er)|cigarette|bidi)\b"),
    ("obesity", r"\b(?:obese|obesity|overweight)\b"),
]

_ALL_TAGS = {tag for tag, _ in CONDITION_PATTERNS}


def detect_conditions(conditions: Any) -> list[str]:
    """Map free-text conditions/history onto canonical tags (tag input passes
    through unchanged, so callers may send tags directly)."""
    items = as_list(conditions)
    text = _joined(items)
    tags: list[str] = []
    for item in items:
        key = item.strip().lower().replace(" ", "_")
        if key in _ALL_TAGS and key not in tags:
            tags.append(key)
    for tag, pattern in CONDITION_PATTERNS:
        if tag not in tags and re.search(pattern, text):
            tags.append(tag)
    return tags


# ---------------------------------------------------------------------------
# Lab thresholds → tags (so both condition- and lab-driven rules share a path)
# ---------------------------------------------------------------------------

def _lab(labs: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key in labs:
            try:
                return float(labs[key])
            except (TypeError, ValueError):
                continue
    return None


def lab_tags(labs: dict[str, Any] | None) -> dict[str, float]:
    """Derived tags from numeric findings. Returns only what is derivable."""
    labs = labs or {}
    tags: dict[str, float] = {}
    egfr = _lab(labs, "egfr", "gfr")
    k = _lab(labs, "potassium", "k")
    na = _lab(labs, "sodium", "na")
    hb = _lab(labs, "hemoglobin", "haemoglobin", "hb")
    plt = _lab(labs, "platelets", "platelet")
    ldl = _lab(labs, "ldl", "ldl_c")
    troponin = _lab(labs, "troponin", "troponin_i", "troponin_t", "troponin_flag")
    lvef = _lab(labs, "lvef", "ef")
    alt = _lab(labs, "alt", "sgpt")
    if egfr is not None:
        if egfr < 30:
            tags["renal_severe"] = egfr
        elif egfr < 60:
            tags["renal_impairment"] = egfr
    if k is not None:
        if k > 5.5:
            tags["hyperkalemia"] = k
        elif k >= 5.0:
            tags["borderline_hyperkalemia"] = k
        elif k < 3.5:
            tags["hypokalemia"] = k
    if na is not None and na < 130:
        tags["hyponatremia"] = na
    if hb is not None and hb < 10:
        tags["anemia"] = hb
    if plt is not None and plt < 100:
        tags["thrombocytopenia"] = plt
    if ldl is not None and ldl >= 160:
        tags["dyslipidemia_lab"] = ldl
    if troponin is not None and troponin > 0.04:
        tags["troponin_elevated"] = troponin
    if lvef is not None and lvef < 40:
        tags["reduced_ef"] = lvef
    if alt is not None and alt > 120:
        tags["transaminitis"] = alt
    return tags

