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


# ---------------------------------------------------------------------------
# Drug table — one curated entry per option the workspace can offer
# ---------------------------------------------------------------------------
# indications   : presentation/condition tags that make this drug worth offering
# avoid         : (tag, severity, note) — severity "absolute" removes it,
#                 "relative" keeps it listed but blocked-with-review
# caution       : (tag, note) — offered with an explicit review flag
# lab_guards    : (lab_tag, severity, note) evaluated against lab_tags()
# allergens     : hard allergy matches (drug + class),
# allergen_soft : cross-reactivity that deserves a flag, not a block

DRUGS: list[dict[str, Any]] = [
    {
        "key": "aspirin",
        "name": "Aspirin",
        "drug_class": "antiplatelet",
        "priority": 1,
        "indications": ["suspected_acs", "established_cad", "prior_mi", "prior_pci_cabg", "cerebrovascular_disease"],
        "avoid": [("peptic_ulcer", "relative", "Active or recent peptic ulcer/GI bleed — add gastroprotection or choose another agent.")],
        "caution": [
            ("bleeding_risk", "Bleeding tendency — weigh against ischaemic risk and review platelet count."),
            ("gout", "Low-dose aspirin can raise urate — monitor in gout."),
        ],
        "lab_guards": [
            ("thrombocytopenia", "relative", "Platelets <100 ×10⁹/L — bleeding risk; discuss with the prescriber before starting."),
            ("anemia", "relative", "Haemoglobin <10 g/dL — investigate the cause before adding an antithrombotic."),
        ],
        "allergens": ["aspirin", "asa", "acetylsalicylic", "salicylate", "salicylates", "nsaid", "nsaids", "disprin", "ecosprin"],
        "monitoring": ["Bleeding signs (bruising, melena) at each review", "Haemoglobin if anaemic or on dual therapy"],
        "dose_note": "Suspected ACS: 162–325 mg chewed at presentation, then 75–100 mg once daily.",
        "evidence": "ACC/AHA chest pain guideline — aspirin for suspected ACS unless contraindicated.",
    },
    {
        "key": "clopidogrel",
        "name": "Clopidogrel (P2Y12 inhibitor)",
        "drug_class": "p2y12",
        "priority": 2,
        "indications": ["suspected_acs", "prior_pci_cabg"],
        "avoid": [
            ("bleeding_risk", "absolute", "Active bleeding tendency — dual antiplatelet therapy is unsafe without specialist review."),
            ("peptic_ulcer", "relative", "Recent GI bleed — only with gastroprotection and a defined duration."),
        ],
        "caution": [("peptic_ulcer", "Add a proton-pump inhibitor while on dual therapy.")],
        "lab_guards": [("thrombocytopenia", "relative", "Platelets <100 ×10⁹/L — bleeding risk on dual antiplatelet therapy.")],
        "allergens": ["clopidogrel", "plavix", "p2y12", "ticagrelor", "prasugrel"],
        "monitoring": ["Bleeding signs", "Adherence/duration per stent protocol"],
        "dose_note": "300–600 mg loading then 75 mg daily, per ACS/PCI protocol and bleeding risk.",
        "evidence": "ACC/AHA ACS guideline — P2Y12 inhibitor added to aspirin for ACS or after PCI.",
    },
    {
        "key": "statin_high_intensity",
        "name": "High-intensity statin (atorvastatin/rosuvastatin)",
        "drug_class": "statin",
        "priority": 2,
        "indications": ["suspected_acs", "established_cad", "prior_mi", "prior_pci_cabg", "dyslipidemia", "dyslipidemia_lab", "diabetes", "cerebrovascular_disease"],
        "avoid": [
            ("pregnancy", "absolute", "Statins are contraindicated in pregnancy and breastfeeding."),
            ("liver_disease", "relative", "Active hepatic disease — check transaminases before starting."),
        ],
        "caution": [
            ("diabetes", "Statin therapy can modestly raise glucose — benefit still outweighs it in established ASCVD."),
            ("obstructive_airway_disease", "No interaction expected; included only if the airway disease is being treated with theophylline."),
        ],
        "lab_guards": [("transaminitis", "relative", "ALT >3× upper limit — investigate before starting a high-intensity statin.")],
        "allergens": ["statin", "statins", "atorvastatin", "rosuvastatin", "simvastatin", "lipitor", "crestor"],
        "monitoring": ["Lipid panel at 6–8 weeks", "ALT if symptomatic", "Muscle symptoms (myopathy)"],
        "dose_note": "Atorvastatin 40–80 mg nightly, or rosuvastatin 20–40 mg — high intensity for ASCVD/ACS.",
        "evidence": "AHA/ACC cholesterol guideline — high-intensity statin for established ASCVD and ACS.",
    },
    {
        "key": "beta_blocker",
        "name": "Beta-blocker (metoprolol/bisoprolol/carvedilol)",
        "drug_class": "beta_blocker",
        "priority": 3,
        "indications": ["suspected_acs", "established_cad", "prior_mi", "heart_failure", "reduced_ef", "atrial_fibrillation"],
        "avoid": [
            ("bradyarrhythmia", "absolute", "Bradycardia, AV block or sick sinus syndrome without a pacemaker."),
            ("obstructive_airway_disease", "relative", "Asthma/COPD — a cardioselective agent at low dose only if the benefit is clear; review for bronchospasm."),
        ],
        "caution": [
            ("diabetes", "Beta-blockade can mask hypoglycaemia awareness — counsel the patient."),
            ("heart_failure", "Start low and titrate slowly; avoid in acute decompensation until stable."),
        ],
        "lab_guards": [],
        "allergens": ["beta blocker", "beta-blocker", "metoprolol", "bisoprolol", "carvedilol", "atenolol", "lopressor", "betaloc"],
        "monitoring": ["Heart rate and blood pressure", "Symptoms of fatigue/bronchospasm"],
        "dose_note": "Metoprolol succinate 25–50 mg daily (or bisoprolol 2.5–5 mg) once haemodynamically stable.",
        "evidence": "Beta-blockade after ACS/for stable CAD and HFrEF (guideline-directed medical therapy).",
    },
    {
        "key": "ace_inhibitor",
        "name": "ACE inhibitor (ramipril/lisinopril)",
        "drug_class": "ace_inhibitor",
        "priority": 3,
        "indications": ["heart_failure", "reduced_ef", "prior_mi", "hypertension", "diabetes", "chronic_kidney_disease"],
        "avoid": [
            ("pregnancy", "absolute", "ACE inhibitors are contraindicated in pregnancy — fetal renal toxicity."),
            ("hyperkalemia", "absolute", "Do not start with K+ >5.5 mmol/L — correct potassium first."),
        ],
        "caution": [
            ("chronic_kidney_disease", "Expect a small creatinine rise; recheck at 1–2 weeks and stop if it exceeds 30%."),
            ("borderline_hyperkalemia", "K+ 5.0–5.5 mmol/L — recheck potassium and creatinine after 1 week."),
            ("bilateral_renal_artery_stenosis", "Avoid if bilateral renal artery stenosis is known."),
        ],
        "lab_guards": [
            ("renal_severe", "relative", "eGFR <30 mL/min — start at the lowest dose with close renal and potassium follow-up."),
        ],
        "allergens": ["ace inhibitor", "ace-inhibitor", "acei", "ramipril", "lisinopril", "enalapril", "captopril", "angioedema"],
        "monitoring": ["Potassium and creatinine at 1–2 weeks", "Cough and angioedema", "Blood pressure"],
        "dose_note": "Ramipril 2.5 mg daily, titrate to 10 mg (or lisinopril 5→20 mg) as tolerated.",
        "evidence": "RAAS blockade for hypertension, HFrEF and CAD with diabetes or CKD.",
    },
    {
        "key": "arb",
        "name": "ARB (losartan/valsartan)",
        "drug_class": "arb",
        "priority": 4,
        "indications": ["heart_failure", "reduced_ef", "hypertension", "diabetes", "chronic_kidney_disease"],
        "avoid": [
            ("pregnancy", "absolute", "ARBs are contraindicated in pregnancy."),
            ("hyperkalemia", "absolute", "Do not start with K+ >5.5 mmol/L — correct potassium first."),
        ],
        "caution": [("chronic_kidney_disease", "Recheck creatinine and potassium at 1–2 weeks; stop if creatinine rises >30%.")],
        "lab_guards": [("renal_severe", "relative", "eGFR <30 mL/min — lowest dose with close follow-up.")],
        "allergens": ["arb", "angiotensin receptor blocker", "losartan", "valsartan", "irbesartan", "candesartan"],
        "monitoring": ["Potassium and creatinine at 1–2 weeks", "Blood pressure"],
        "dose_note": "Losartan 50 mg daily (or valsartan 80 mg) — the alternative when an ACE inhibitor causes cough.",
        "evidence": "ARBs where ACE inhibitors are not tolerated; same RAAS indications.",
    },
    {
        "key": "ccb",
        "name": "Calcium-channel blocker (amlodipine)",
        "drug_class": "ccb",
        "priority": 5,
        "indications": ["hypertension", "established_cad"],
        "avoid": [("aortic_stenosis", "relative", "Severe aortic stenosis — vasodilatation can cause syncope; specialist review.")],
        "caution": [("heart_failure", "Amlodipine is acceptable; verapamil/diltiazem are not in HFrEF.")],
        "lab_guards": [],
        "allergens": ["ccb", "calcium channel blocker", "amlodipine", "nifedipine", "diltiazem", "verapamil"],
        "monitoring": ["Blood pressure", "Ankle oedema"],
        "dose_note": "Amlodipine 5–10 mg once daily.",
        "evidence": "First-line antihypertensive class; add-on for angina when beta-blockade is unsuitable.",
    },
    {
        "key": "loop_diuretic",
        "name": "Loop diuretic (furosemide)",
        "drug_class": "loop_diuretic",
        "priority": 2,
        "indications": ["congestion", "heart_failure"],
        "avoid": [],
        "caution": [
            ("chronic_kidney_disease", "Higher doses may be needed; monitor renal function and electrolytes."),
            ("hypokalemia", "K+ <3.5 mmol/L — replace potassium and recheck before/with diuresis."),
            ("hyponatremia", "Sodium <130 mmol/L — review the cause and senior advice before aggressive diuresis."),
        ],
        "lab_guards": [("hyponatremia", "relative", "Sodium <130 mmol/L — review diuretic strategy.")],
        "allergens": ["furosemide", "lasix", "bumetanide", "torasemide"],
        "allergen_soft": ["sulfa", "sulfonamide", "sulfonamides", "sulfa drugs"],
        "monitoring": ["Weight and urine output", "Potassium, sodium and creatinine"],
        "dose_note": "Furosemide 20–40 mg once daily for congestion; adjust to weight and urine output.",
        "evidence": "Guideline-directed decongestion in heart failure with volume overload.",
    },
    {
        "key": "mra",
        "name": "Mineralocorticoid receptor antagonist (spironolactone)",
        "drug_class": "mra",
        "priority": 4,
        "indications": ["heart_failure", "reduced_ef"],
        "avoid": [
            ("hyperkalemia", "absolute", "K+ >5.5 mmol/L or eGFR <30 — hyperkalaemia risk is unacceptable."),
            ("renal_severe", "absolute", "eGFR <30 mL/min — do not start."),
        ],
        "caution": [
            ("borderline_hyperkalemia", "K+ 5.0–5.5 mmol/L — recheck potassium and creatinine at 1 and 4 weeks."),
            ("chronic_kidney_disease", "Dose-reduce and monitor potassium closely."),
        ],
        "lab_guards": [("renal_severe", "absolute", "eGFR <30 mL/min — do not start.")],
        "allergens": ["spironolactone", "eplerenone", "mra"],
        "monitoring": ["Potassium and creatinine at 1 and 4 weeks", "Gynaecomastia"],
        "dose_note": "Spironolactone 12.5–25 mg daily when EF is reduced and potassium/eGFR allow.",
        "evidence": "MRA for HFrEF; the potassium/eGFR gates come from that trial population.",
    },
    {
        "key": "sglt2_inhibitor",
        "name": "SGLT2 inhibitor (dapagliflozin/empagliflozin)",
        "drug_class": "sglt2_inhibitor",
        "priority": 5,
        "indications": ["heart_failure", "reduced_ef", "diabetes", "chronic_kidney_disease"],
        "avoid": [("pregnancy", "absolute", "SGLT2 inhibitors are not used in pregnancy.")],
        "caution": [
            ("chronic_kidney_disease", "eGFR-based initiation thresholds apply — check current eGFR."),
            ("hypotension", "Volume-depleted patients: reduce diuretic before starting."),
        ],
        "lab_guards": [("renal_severe", "relative", "eGFR <20 mL/min — benefits/dose depend on the specific agent; specialist review.")],
        "allergens": ["sglt2", "sglt2 inhibitor", "dapagliflozin", "empagliflozin", "canagliflozin"],
        "monitoring": ["eGFR and potassium", "Genital infections", "Volume status / blood pressure", "Ketoacidosis symptoms"],
        "dose_note": "Dapagliflozin 10 mg daily (empagliflozin 10 mg) once eGFR allows.",
        "evidence": "SGLT2 inhibitor for heart failure and diabetes with cardiovascular disease.",
    },
    {
        "key": "nitrate",
        "name": "Nitrate (sublingual GTN)",
        "drug_class": "nitrate",
        "priority": 1,
        "indications": ["suspected_acs", "established_cad"],
        "avoid": [("aortic_stenosis", "relative", "Severe aortic stenosis — nitrates can cause profound hypotension.")],
        "caution": [("hypotension", "Avoid if systolic BP <100 mmHg; review every dose.")],
        "lab_guards": [],
        "allergens": ["nitrate", "nitrates", "nitroglycerin", "glyceryl trinitrate", "gtn", "isosorbide"],
        "monitoring": ["Blood pressure and heart rate after each dose", "Headache (expected)"],
        "dose_note": "Sublingual GTN 0.4 mg as needed for ongoing ischaemic pain — screen for PDE5 inhibitors first.",
        "evidence": "ACC/AHA chest pain guideline — nitrates for ischaemic pain, contraindicated with PDE5 inhibitors.",
    },
    {
        "key": "anticoagulant",
        "name": "Anticoagulant (apixaban/warfarin)",
        "drug_class": "anticoagulant",
        "priority": 3,
        "indications": ["atrial_fibrillation", "cerebrovascular_disease"],
        "avoid": [
            ("bleeding_risk", "absolute", "Known bleeding disorder or thrombocytopenia — anticoagulate only with specialist input."),
            ("peptic_ulcer", "relative", "Recent GI bleed — do not anticoagulate until reviewed and gastroprotection is in place."),
            ("pregnancy", "relative", "Pregnancy: warfarin is teratogenic; needs specialist-led anticoagulation planning."),
        ],
        "caution": [
            ("chronic_kidney_disease", "Renal function drives dose and choice — recalculate the dose at every review."),
            ("anemia", "Investigate the cause of anaemia before starting."),
        ],
        "lab_guards": [
            ("renal_severe", "relative", "eGFR <30 mL/min — dose-reduce or choose per agent; eGFR <15 usually excludes DOACs."),
            ("thrombocytopenia", "relative", "Platelets <100 ×10⁹/L — bleeding risk."),
            ("anemia", "relative", "Haemoglobin <10 g/dL — investigate before anticoagulating."),
        ],
        "allergens": ["anticoagulant", "warfarin", "apixaban", "rivaroxaban", "edoxaban", "dabigatran", "heparin", "coumadin"],
        "monitoring": ["Haemoglobin, platelets and renal function at baseline and intervals", "Bleeding signs", "INR if warfarin", "CHA₂DS₂-VASc review"],
        "dose_note": "Apixaban 5 mg twice daily (2.5 mg when 2 of: age ≥80, weight ≤60 kg, creatinine ≥1.5 mg/dL).",
        "evidence": "CHA₂DS₂-VASc-guided anticoagulation for atrial fibrillation or prior thromboembolism.",
    },
    {
        "key": "metformin",
        "name": "Metformin",
        "drug_class": "biguanide",
        "priority": 5,
        "indications": ["diabetes"],
        "avoid": [
            ("renal_severe", "absolute", "eGFR <30 mL/min — do not start; review continuation if already on it."),
            ("acidosis_risk", "relative", "Any acute illness with dehydration, hypoxia or sepsis — hold and reassess."),
        ],
        "caution": [("renal_impairment", "eGFR 30–45 mL/min: lower dose, do not titrate up, and review more often.")],
        "lab_guards": [("renal_severe", "absolute", "eGFR <30 mL/min — metformin is contraindicated.")],
        "allergens": ["metformin"],
        "monitoring": ["eGFR every 3–6 months", "B12 if long-term use", "Gastrointestinal tolerance"],
        "dose_note": "Metformin 500 mg once or twice daily with food, titrated slowly; hold for contrast studies or acute illness.",
        "evidence": "First-line glucose-lowering therapy in type 2 diabetes with cardiovascular disease.",
    },
    {
        "key": "ppi",
        "name": "Proton-pump inhibitor (pantoprazole)",
        "drug_class": "ppi",
        "priority": 6,
        "indications": ["antithrombotic_bleeding_risk"],
        "avoid": [],
        "caution": [],
        "lab_guards": [],
        "allergens": ["ppi", "proton pump inhibitor", "omeprazole", "pantoprazole", "esomeprazole", "lansoprazole"],
        "monitoring": ["Indication for continuing after the bleeding-risk period ends"],
        "dose_note": "Pantoprazole 20–40 mg daily while on antithrombotic therapy (preferred over omeprazole with clopidogrel).",
        "evidence": "Gastroprotection when antiplatelet/anticoagulant bleeding risk is elevated (age, ulcer history, dual therapy).",
    },
    {
        "key": "digoxin",
        "name": "Digoxin",
        "drug_class": "cardiac_glycoside",
        "priority": 6,
        "indications": ["atrial_fibrillation_symptomatic"],
        "avoid": [("bradyarrhythmia", "relative", "Bradycardia or AV block — avoid or use with pacing/specialist review.")],
        "caution": [
            ("chronic_kidney_disease", "Renal clearance — use lower doses and check levels."),
            ("hypokalemia", "Hypokalaemia potentiates digoxin toxicity — correct potassium."),
        ],
        "lab_guards": [("renal_severe", "relative", "eGFR <30 mL/min — reduce dose and monitor levels.")],
        "allergens": ["digoxin", "digitalis"],
        "monitoring": ["Digoxin level", "Potassium and renal function", "Bradycardia or nausea (toxicity)"],
        "dose_note": "Digoxin 0.125–0.25 mg daily (lower if elderly or renal impairment).",
        "evidence": "Rate control in atrial fibrillation when beta-blockade is contraindicated or insufficient.",
    },
    {
        "key": "amiodarone",
        "name": "Amiodarone",
        "drug_class": "antiarrhythmic",
        "priority": 7,
        "indications": ["atrial_fibrillation_symptomatic"],
        "avoid": [("liver_disease", "relative", "Hepatic disease — hepatotoxicity risk; specialist review.")],
        "caution": [("obstructive_airway_disease", "Pulmonary toxicity risk is higher with pre-existing lung disease.")],
        "lab_guards": [],
        "allergens": ["amiodarone", "iodine", "iodinated"],
        "monitoring": ["Thyroid function and LFTs every 6 months", "ECG (QT)", "Annual ophthalmology review"],
        "dose_note": "Specialist-led loading then 200 mg daily — long-term toxicity limits duration.",
        "evidence": "Rhythm control in atrial fibrillation when rate control fails or symptoms persist.",
    },
    {
        "key": "nsaid",
        "name": "NSAIDs (ibuprofen/diclofenac)",
        "drug_class": "nsaid",
        "priority": 8,
        "indications": ["avoid_advice"],
        "avoid": [],
        "caution": [],
        "lab_guards": [],
        "allergens": ["nsaid", "nsaids", "ibuprofen", "diclofenac", "naproxen", "aspirin", "salicylate"],
        "monitoring": [],
        "dose_note": "Avoid; use paracetamol for analgesia in this profile.",
        "evidence": "NSAIDs raise bleeding, renal and heart-failure risk in the flagged profiles below.",
    },
]

_DRUG_BY_KEY = {d["key"]: d for d in DRUGS}
_CLASS_OF = {d["key"]: d["drug_class"] for d in DRUGS}

# Current-medication aliases (incl. common brands) → internal drug key.
# Used for interaction screening and "already documented" detection.
MED_ALIASES: dict[str, tuple[str, ...]] = {
    "aspirin": ("aspirin", "asa", "acetylsalicylic", "disprin", "ecosprin", "aspilet", "aspin", "salicylate"),
    "clopidogrel": ("clopidogrel", "plavix", "ticagrelor", "brilinta", "prasugrel", "effient"),
    "statin_high_intensity": ("atorvastatin", "rosuvastatin", "simvastatin", "pravastatin", "statin", "lipitor", "crestor", "zocor"),
    "beta_blocker": ("metoprolol", "bisoprolol", "carvedilol", "atenolol", "nebivolol", "propranolol", "lopressor", "betaloc", "concor"),
    "ace_inhibitor": ("ramipril", "lisinopril", "enalapril", "captopril", "perindopril", "trandolapril", "ace inhibitor", "acei"),
    "arb": ("losartan", "valsartan", "irbesartan", "candesartan", "telmisartan", "olmesartan", "arb"),
    "ccb": ("amlodipine", "nifedipine", "diltiazem", "verapamil", "lercanidipine", "norvasc"),
    "loop_diuretic": ("furosemide", "lasix", "bumetanide", "torasemide", "torsemide"),
    "mra": ("spironolactone", "eplerenone", "aldactone"),
    "sglt2_inhibitor": ("dapagliflozin", "empagliflozin", "canagliflozin", "ertugliflozin", "forxiga", "jardiance"),
    "nitrate": ("nitroglycerin", "glyceryl trinitrate", "gtn", "nitro", "isosorbide", "imdur"),
    "anticoagulant": ("warfarin", "coumadin", "apixaban", "eliquis", "rivaroxaban", "xarelto", "edoxaban", "dabigatran", "pradaxa", "heparin", "enoxaparin", "clexane"),
    "metformin": ("metformin", "glucophage", "glucovance"),
    "ppi": ("omeprazole", "pantoprazole", "esomeprazole", "lansoprazole", "rabeprazole", "nexium", "losec"),
    "digoxin": ("digoxin", "digoxin", "digitalis", "lanoxin"),
    "amiodarone": ("amiodarone", "cordarone"),
    "nsaid": ("ibuprofen", "brufen", "diclofenac", "voltaren", "naproxen", "mefenamic", "celecoxib", "etoricoxib", "ketorolac"),
    "pde5_inhibitor": ("sildenafil", "viagra", "tadalafil", "cialis", "vardenafil"),
    "nd_ccb": ("verapamil", "diltiazem", "isoptin", "dilzem"),
    "biguanide": ("metformin", "glucophage"),
}

_CLASS_ALIASES: dict[str, str] = {
    key: _DRUG_BY_KEY[key]["drug_class"]
    for key in _DRUG_BY_KEY
}


def current_med_keys(current_medications: Any) -> list[str]:
    """Match documented medications (names or brands) to internal drug keys."""
    text = _joined(as_list(current_medications))
    found: list[str] = []
    for key, aliases in MED_ALIASES.items():
        if key not in found and any(_has(text, alias) for alias in aliases):
            found.append(key)
    return found


def allergy_matches(allergies: Any, drug: dict[str, Any]) -> list[str]:
    """Allergy terms the patient reported that name this drug or its class."""
    text = _joined(as_list(allergies))
    hits = [term for term in drug.get("allergens", []) if _has(text, term)]
    return hits


def soft_allergy_matches(allergies: Any, drug: dict[str, Any]) -> list[str]:
    """Cross-reactivity the clinician should know about, not a hard block."""
    text = _joined(as_list(allergies))
    return [term for term in drug.get("allergen_soft", []) if _has(text, term)]


# What to do instead when an allergy blocks the first-line agent: the allergy
# must resolve the therapy question, not silently cancel it.
_ALLERGY_ALTERNATIVES: dict[str, str] = {
    "aspirin": "For suspected ACS/PCI, a P2Y12 inhibitor alone (below) is the usual aspirin-free route — confirm with the institutional ACS protocol.",
    "clopidogrel": "If a P2Y12 inhibitor is essential (post-PCI), ticagrelor or prasugrel are alternatives — specialist input required.",
    "statin_high_intensity": "Do not rechallenge a true statin allergy: consider a different statin only after reviewing the reaction, or a non-statin lipid-lowering option with specialist input.",
    "ace_inhibitor": "An ARB is the standard substitute for ACE-inhibitor cough — but any angioedema history needs specialist advice before starting *any* RAAS agent.",
    "arb": "Switch to an ACE inhibitor only if the reaction is not angioedema; otherwise specialist review for a non-RAAS strategy.",
    "beta_blocker": "Review the reaction before considering a cardioselective agent; rate control may need ivabradine or specialist input.",
    "anticoagulant": "Anticoagulation still needs solving — discuss DOAC versus warfarin with the prescriber rather than omitting it.",
    "nitrate": "No nitrates: use anti-ischaemic alternatives (beta-blocker, calcium-channel blocker) and review analgesia.",
    "nsaid": "Use paracetamol for analgesia.",
    "loop_diuretic": "If diuresis is needed, bumetanide/torasemide or a thiazide may be considered after reviewing the reaction history.",
    "metformin": "Consider another glucose-lowering agent — an SGLT2 inhibitor where it is indicated.",
    "mra": "Potassium-sparing alternatives are limited; discuss with the prescriber rather than omitting mineralocorticoid blockade silently.",
    "sglt2_inhibitor": "Consider another agent if glucose lowering is the goal; heart-failure benefit is lost, so document why it was not used.",
    "digoxin": "Rate control without digoxin: beta-blocker or calcium-channel blocker, or specialist rhythm-management input.",
    "amiodarone": "Iodine/amiodarone allergy: rhythm management needs specialist input (alternative antiarrhythmics or ablation).",
    "ppi": "Use an H2 receptor antagonist or antacid for gastroprotection with specialist input.",
}


# ---------------------------------------------------------------------------
# Interaction table (drug key or drug class on either side)
# ---------------------------------------------------------------------------

INTERACTIONS: list[dict[str, str]] = [
    {"a": "p2y12", "b": "anticoagulant", "severity": "major",
     "note": "P2Y12 inhibitor plus anticoagulant markedly increases bleeding (and the risk compounds with aspirin).",
     "action": "Use only with a defined indication and stop date; add gastroprotection and review at each visit."},
    {"a": "aspirin", "b": "anticoagulant", "severity": "major",
     "note": "Antiplatelet plus anticoagulant roughly doubles major bleeding.",
     "action": "Combine only with a clear indication (e.g. recent stent); add gastroprotection and set a stop date."},
    {"a": "aspirin", "b": "p2y12", "severity": "major",
     "note": "Dual antiplatelet therapy raises bleeding without benefit outside ACS/PCI.",
     "action": "Use only per ACS/PCI protocol, and document the planned duration."},
    {"a": "aspirin", "b": "nsaid", "severity": "major",
     "note": "NSAID plus antiplatelet increases GI bleeding and renal risk.",
     "action": "Avoid NSAIDs; use paracetamol for analgesia."},
    {"a": "nsaid", "b": "anticoagulant", "severity": "major",
     "note": "NSAID plus anticoagulant substantially increases GI and intracranial bleeding.",
     "action": "Avoid NSAIDs; if unavoidable add gastroprotection (generally not recommended)."},
    {"a": "nsaid", "b": "ace_inhibitor", "severity": "moderate",
     "note": "NSAIDs blunt antihypertensive effect and can worsen renal function.",
     "action": "Avoid where possible; if used, check creatinine and potassium within a week."},
    {"a": "nsaid", "b": "arb", "severity": "moderate",
     "note": "NSAIDs blunt ARB effect and can worsen renal function.",
     "action": "Avoid where possible; monitor renal function if used."},
    {"a": "nsaid", "b": "loop_diuretic", "severity": "moderate",
     "note": "NSAIDs reduce diuretic efficacy ('triple whammy' with a RAAS blocker).",
     "action": "Avoid; review diuretic dose if NSAIDs are unavoidable."},
    {"a": "ace_inhibitor", "b": "mra", "severity": "major",
     "note": "RAAS blocker plus MRA increases hyperkalaemia risk.",
     "action": "Check potassium and creatinine at 1 and 4 weeks; stop if K+ >5.5 mmol/L."},
    {"a": "arb", "b": "mra", "severity": "major",
     "note": "RAAS blocker plus MRA increases hyperkalaemia risk.",
     "action": "Check potassium and creatinine at 1 and 4 weeks."},
    {"a": "ace_inhibitor", "b": "arb", "severity": "major",
     "note": "Dual RAAS blockade adds hyperkalaemia and renal injury without outcome benefit.",
     "action": "Use one agent only."},
    {"a": "beta_blocker", "b": "nd_ccb", "severity": "major",
     "note": "Beta-blocker plus verapamil/diltiazem causes bradycardia, heart block and hypotension.",
     "action": "Avoid the combination; amlodipine is the safe calcium-channel option here."},
    {"a": "statin_high_intensity", "b": "amiodarone", "severity": "major",
     "note": "Amiodarone raises simvastatin/atorvastatin exposure — myopathy/rhabdomyolysis risk.",
     "action": "Cap simvastatin at 20 mg, or switch to rosuvastatin/pravastatin and warn about muscle pain."},
    {"a": "amiodarone", "b": "anticoagulant", "severity": "major",
     "note": "Amiodarone raises warfarin INR and DOAC exposure (P-gp inhibition).",
     "action": "Reduce the anticoagulant dose and monitor INR/bleeding closely."},
    {"a": "amiodarone", "b": "digoxin", "severity": "major",
     "note": "Amiodarone approximately doubles digoxin levels.",
     "action": "Halve the digoxin dose and check the level."},
    {"a": "digoxin", "b": "loop_diuretic", "severity": "moderate",
     "note": "Diuretic-induced hypokalaemia potentiates digoxin toxicity.",
     "action": "Monitor potassium and digoxin level; replace potassium as needed."},
    {"a": "nitrate", "b": "pde5_inhibitor", "severity": "major",
     "note": "Nitrate plus a PDE5 inhibitor (sildenafil/tadalafil) causes profound hypotension.",
     "action": "Contraindicated — separate by at least 24 h (48 h for tadalafil) and counsel the patient."},
    {"a": "clopidogrel", "b": "ppi", "severity": "moderate",
     "note": "Omeprazole (not pantoprazole) reduces clopidogrel activation via CYP2C19.",
     "action": "Use pantoprazole when gastroprotection is needed alongside clopidogrel."},
    {"a": "metformin", "b": "loop_diuretic", "severity": "moderate",
     "note": "Diuretic-induced volume depletion raises the risk of metformin-associated lactic acidosis.",
     "action": "Hold metformin during acute illness or aggressive diuresis."},
]


def _present_keys(recommended: list[str], current: list[str]) -> set[str]:
    present = set(current)
    for key in recommended:
        present.add(key)
        present.add(_CLASS_OF.get(key, ""))
    for key in list(current):
        present.add(_CLASS_OF.get(key, ""))
    present.discard("")
    return present


def interaction_alerts(recommended_keys: list[str], current_keys: list[str]) -> list[dict[str, str]]:
    """Flag interactions among offered options and documented medications."""
    present = _present_keys(recommended_keys, current_keys)
    alerts: list[dict[str, str]] = []
    for rule in INTERACTIONS:
        a, b = rule["a"], rule["b"]
        if not (a in present and b in present):
            continue
        on_board = sorted({k for k in recommended_keys + current_keys if k == a or k == b or _CLASS_OF.get(k) in (a, b)})
        # Do not flag a drug against itself (e.g. class and key resolving to one agent).
        if len(on_board) < 2 or set(on_board) == {a} or set(on_board) == {b}:
            continue
        alerts.append({
            "pair": [a, b],
            "drugs": on_board,
            "severity": rule["severity"],
            "note": rule["note"],
            "action": rule["action"],
        })
    order = {"major": 0, "moderate": 1}
    alerts.sort(key=lambda item: (order.get(item["severity"], 2), item["pair"][0]))
    return alerts


# ---------------------------------------------------------------------------
# Indications from the presentation
# ---------------------------------------------------------------------------

def indications_from_presentation(symptoms: list[str], tags: list[str], derived: dict[str, float],
                                  risk_level: str | None = None) -> dict[str, str]:
    """Indication → the captured fact that triggered it (never inferred silently)."""
    got: dict[str, str] = {}
    symptoms = [s.lower() for s in symptoms]

    def add(name: str, reason: str) -> None:
        got.setdefault(name, reason)

    for tag in tags:
        if tag == "prior_mi":
            add("prior_mi", "history of myocardial infarction")
        if tag == "prior_pci_cabg":
            add("prior_pci_cabg", "previous PCI/stent or CABG")
        if tag == "established_cad":
            add("established_cad", "known coronary artery disease/angina")
        if tag == "heart_failure":
            add("heart_failure", "documented heart failure")
        if tag == "atrial_fibrillation":
            add("atrial_fibrillation", "documented atrial fibrillation")
            add("atrial_fibrillation_symptomatic", "atrial fibrillation needs a rate/rhythm plan")
        if tag == "hypertension":
            add("hypertension", "hypertension in the history")
        if tag == "diabetes":
            add("diabetes", "diabetes in the history")
        if tag == "chronic_kidney_disease":
            add("chronic_kidney_disease", "chronic kidney disease in the history")
        if tag == "dyslipidemia":
            add("dyslipidemia", "dyslipidaemia in the history")
        if tag == "cerebrovascular_disease":
            add("cerebrovascular_disease", "prior stroke/TIA")

    if "chest pain" in symptoms:
        add("suspected_acs", "chest pain reported (suspected acute coronary syndrome)")
    if "shortness of breath" in symptoms or "leg swelling" in symptoms:
        add("congestion", "breathlessness/leg swelling suggests volume overload")
    if "palpitations" in symptoms and "atrial_fibrillation" not in got:
        add("atrial_fibrillation_symptomatic", "palpitations reported — needs a rhythm assessment before any agent is chosen")
    if derived.get("reduced_ef") is not None:
        add("reduced_ef", f"LVEF {derived['reduced_ef']:g}%")
    if derived.get("dyslipidemia_lab") is not None:
        add("dyslipidemia_lab", f"LDL {derived['dyslipidemia_lab']:g} mg/dL")
    if derived.get("troponin_elevated") is not None:
        add("suspected_acs", "troponin above the reference limit")
    return got


# ---------------------------------------------------------------------------
# The review
# ---------------------------------------------------------------------------

def _antithrombotic_bleeding_risk(tags: list[str], current: list[str], age: int | None) -> str | None:
    reasons = []
    if "peptic_ulcer" in tags:
        reasons.append("GI bleeding history")
    if age is not None and age >= 75:
        reasons.append("age ≥75")
    if {"anticoagulant", "p2y12"} & set(current):
        reasons.append("concurrent antithrombotic therapy")
    return ", ".join(reasons) if reasons else None


def review_medications(
    symptoms: list[str] | None = None,
    *,
    conditions: Any = None,
    allergies: Any = None,
    current_medications: Any = None,
    age: int | float | None = None,
    sex: str | None = None,
    risk_level: str | None = None,
    labs: dict[str, Any] | None = None,
    pregnancy: bool | None = None,
) -> dict[str, Any]:
    """Recommend, flag and block medication options from the captured facts."""
    symptom_list = [str(s).strip().lower() for s in (symptoms or []) if str(s).strip()]
    condition_list = as_list(conditions)
    allergy_list = as_list(allergies)
    current_list = as_list(current_medications)
    try:
        age_value = int(age) if age is not None and str(age).strip() != "" else None
    except (TypeError, ValueError):
        age_value = None

    tags = detect_conditions(condition_list)
    if pregnancy:
        tags.append("pregnancy")
    derived = lab_tags(labs)
    indications = indications_from_presentation(symptom_list, tags, derived, risk_level)
    current_keys = current_med_keys(current_list)

    # Gastroprotection becomes an indication when antithrombotic bleeding risk stacks up.
    if _antithrombotic_bleeding_risk(tags, current_keys, age_value):
        indications["antithrombotic_bleeding_risk"] = _antithrombotic_bleeding_risk(tags, current_keys, age_value) or ""

    recommendations: list[dict[str, Any]] = []
    contraindicated: list[dict[str, Any]] = []
    allergy_alerts: list[dict[str, Any]] = []

    for drug in sorted(DRUGS, key=lambda d: (d["priority"], d["name"])):
        key = drug["key"]
        triggered = {name: indications[name] for name in drug["indications"] if name in indications}
        already_on = key in current_keys or drug["drug_class"] in {
            _CLASS_OF.get(k, "") for k in current_keys
        }
        if not triggered and not already_on:
            continue

        hits = allergy_matches(allergy_list, drug)
        blocks: list[dict[str, str]] = []
        if hits:
            blocks.append({
                "kind": "allergy",
                "severity": "absolute",
                "trigger": "reported allergy: " + ", ".join(hits),
                "note": f"Reported allergy matches {drug['name']} — do not use it; choose a structurally different alternative.",
            })
            allergy_alerts.append({
                "drug": drug["name"],
                "drug_class": drug["drug_class"],
                "matched_terms": hits,
                "action": "Do not prescribe this agent; record the allergy in the patient record.",
                "alternative": _ALLERGY_ALTERNATIVES.get(
                    key, "Choose a structurally different class and document the allergy."
                ),
            })
        for tag, severity, note in drug["avoid"]:
            if tag in tags or tag in derived:
                blocks.append({"kind": "condition" if tag in tags else "lab", "severity": severity,
                               "trigger": tag, "note": note})
        for tag, severity, note in drug["lab_guards"]:
            if tag in derived:
                blocks.append({"kind": "lab", "severity": severity, "trigger": tag, "note": note})
        # A condition and its lab tag can both name the same problem — report it once.
        blocks = list({(block["kind"], block["trigger"]): block for block in blocks}.values())

        if blocks:
            hard = [b for b in blocks if b["severity"] == "absolute"]
            contraindicated.append({
                "drug": drug["name"],
                "drug_class": drug["drug_class"],
                "status": "contraindicated" if hard else "review-before-use",
                "severity": "absolute" if hard else "relative",
                "blocks": blocks,
                "already_documented": already_on,
                "note": (
                    "Already documented in the current list — review and consider stopping or "
                    "changing it with the prescriber." if already_on else
                    "Do not start without resolving the flag above."
                ),
                "evidence": drug["evidence"],
            })
            continue

        flags: list[str] = []
        for tag, note in drug["caution"]:
            if tag in tags or tag in derived:
                flags.append(note)
        for term in soft_allergy_matches(allergy_list, drug):
            flags.append(
                f"Reported '{term}' allergy: cross-reactivity with this agent is uncommon but "
                "review the reaction history before prescribing."
            )
        if age_value is not None and age_value >= 75 and drug["drug_class"] in {
            "antiplatelet", "anticoagulant", "p2y12", "nsaid"
        }:
            flags.append("Age ≥75 — higher bleeding risk; confirm dose and gastroprotection.")
        if age_value is not None and age_value >= 80 and drug["drug_class"] in {
            "cardiac_glycoside", "biguanide", "loop_diuretic"
        }:
            flags.append("Age ≥80 — start at a reduced dose and review renal function.")

        recommendations.append({
            "drug": drug["name"],
            "drug_class": drug["drug_class"],
            "status": "already-documented" if already_on else "recommended",
            "priority": drug["priority"],
            "indications": list(triggered.keys()),
            "triggered_by": list(triggered.values()),
            "dose_note": drug["dose_note"],
            "monitoring": drug["monitoring"],
            "review_flags": flags,
            "evidence": drug["evidence"],
            "action": (
                "Already on the list — verify dose, indication and adherence rather than restarting."
                if already_on else "Offer to the clinician for selection and prescription."
            ),
        })

    # One RAAS strategy at a time: combination ACE inhibitor + ARB adds
    # hyperkalaemia and renal injury without outcome benefit, so when both
    # would be offered the ARB is demoted to "only if the ACE inhibitor is
    # not tolerated" instead of being presented as a parallel option.
    offered_keys = [
        key for key in _DRUG_BY_KEY
        if any(rec["drug"] == _DRUG_BY_KEY[key]["name"] for rec in recommendations)
    ]
    raas_on_board = "ace_inhibitor" in offered_keys or "ace_inhibitor" in current_keys
    for rec in recommendations:
        if rec["drug_class"] == "arb" and rec["status"] == "recommended" and raas_on_board:
            rec["status"] = "alternative"
            rec["action"] = (
                "Offer only if the ACE inhibitor is not tolerated (cough or angioedema); "
                "never combine the two."
            )
            rec["review_flags"].append(
                "Dual RAAS blockade adds hyperkalaemia and renal injury without outcome benefit."
            )

    primary_keys = [
        key for key in offered_keys
        if any(
            rec["drug"] == _DRUG_BY_KEY[key]["name"] and rec["status"] != "alternative"
            for rec in recommendations
        )
    ]
    alerts = interaction_alerts(primary_keys, current_keys)

    monitoring: list[str] = []
    for rec in recommendations:
        for item in rec["monitoring"]:
            if item not in monitoring:
                monitoring.append(item)
    for alert in alerts:
        if alert["severity"] == "major" and "Review the flagged combination" not in monitoring:
            monitoring.append("Review the flagged combination before the next dose")

    missing: list[str] = []
    if not allergy_list:
        missing.append("No drug allergies recorded — ask before prescribing (this blocks allergy screening).")
    if age_value is None:
        missing.append("Age not recorded — bleeding and renal dose checks are approximate.")
    if not current_list:
        missing.append("Current medications not recorded — interaction screening is incomplete.")
    if not labs:
        missing.append("No laboratory values supplied (eGFR, potassium) — renal and electrolyte gates were not applied.")
    else:
        if _lab(labs or {}, "egfr", "gfr") is None:
            missing.append("eGFR/creatinine not supplied — renal dose gates were not applied.")
        if _lab(labs or {}, "potassium", "k") is None:
            missing.append("Potassium not supplied — RAAS/MRA safety gates were not applied.")
    if sex and str(sex).lower().startswith("f") and age_value is not None and 15 <= age_value <= 50 and pregnancy is None and "pregnancy" not in tags:
        missing.append("Pregnancy status not recorded for a patient of childbearing age.")

    pathway = _pathway(risk_level, indications, derived)

    if recommendations or contraindicated:
        summary = (
            f"{len(recommendations)} option(s) offered, {len(contraindicated)} blocked or flagged "
            f"for review, {len(alerts)} interaction(s) flagged — based on "
            f"{len(indications)} captured indication(s)."
        )
    else:
        summary = (
            "No captured fact triggers a specific therapy option. Record conditions, allergies and "
            "current medications (or fill the gaps below) before expecting recommendations."
        )

    return {
        "pathway": pathway,
        "indications": [{"name": name, "triggered_by": reason} for name, reason in indications.items()],
        "patient_profile": {
            "age": age_value,
            "sex": sex or None,
            "conditions": tags,
            "condition_text": condition_list,
            "allergies": allergy_list,
            "current_medications": current_list,
            "current_medication_classes": sorted({_CLASS_OF.get(k, k) for k in current_keys}),
            "pregnancy": None if pregnancy is None else bool(pregnancy),
            "labs_considered": derived,
        },
        "recommendations": recommendations,
        "contraindicated": contraindicated,
        "allergy_alerts": allergy_alerts,
        "interaction_alerts": alerts,
        "monitoring_plan": monitoring,
        "missing_information": missing,
        "summary": summary,
        "disclaimer": DISCLAIMER,
    }


def _pathway(risk_level: str | None, indications: dict[str, str], derived: dict[str, float]) -> dict[str, Any]:
    """Urgency of the *encounter*, so medication choices never delay escalation."""
    if derived.get("troponin_elevated") is not None or risk_level == "High":
        return {
            "urgency": "emergency",
            "statement": "Treat as possible acute coronary syndrome: stabilise and escalate on clinical grounds.",
            "rationale": [
                "Screening band is High" if risk_level == "High" else "Troponin is above the reference limit",
                "Do not delay emergency assessment, ECG or biomarkers for outpatient medication titration.",
            ],
        }
    if "suspected_acs" in indications:
        return {
            "urgency": "emergency",
            "statement": "Chest pain reported: treat as possible acute coronary syndrome until excluded.",
            "rationale": ["Chest pain is the trigger for the ACS pathway regardless of the medication options."],
        }
    if risk_level == "Medium":
        return {
            "urgency": "urgent",
            "statement": "Arrange same-day or next-day clinical review; medication changes are for that review.",
            "rationale": ["Screening band is Medium."],
        }
    return {
        "urgency": "routine",
        "statement": "Routine review: options below are for planned, clinician-led prescribing.",
        "rationale": ["No emergency trigger captured in this encounter."],
    }
