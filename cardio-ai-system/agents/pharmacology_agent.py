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
# Sources
# ---------------------------------------------------------------------------
# Every drug entry and every interaction rule names at least one id from this
# table, and `backend/test_pharmacology_agent.py` fails when one does not
# resolve. A citation nobody can follow is the same as no citation, so each
# entry carries the publisher's URL as well as the title. `label` is the FDA
# prescribing information (DailyMed) — the source for CYP/P-gp and dose-limit
# statements that no single guideline lists.

SOURCES: dict[str, dict[str, str]] = {
    "ccd-2023": {
        "title": "2023 AHA/ACC/ACCP/ASPC/NLA/PCNA Guideline for the Management of Patients With Chronic Coronary Disease",
        "url": "https://www.ahajournals.org/doi/10.1161/CIR.0000000000001168",
    },
    "hf-2022": {
        "title": "2022 AHA/ACC/HFSA Guideline for the Management of Heart Failure",
        "url": "https://www.ahajournals.org/doi/10.1161/CIR.0000000000001063",
    },
    "acs-2025": {
        "title": "2025 ACC/AHA/ACEP/NAEMSP/SCAI Guideline for the Management of Patients With Acute Coronary Syndromes",
        "url": "https://www.ahajournals.org/doi/10.1161/CIR.0000000000001309",
    },
    "af-2023": {
        "title": "2023 ACC/AHA/ACCP/HRS Guideline for the Diagnosis and Management of Atrial Fibrillation",
        "url": "https://www.ahajournals.org/doi/10.1161/CIR.0000000000001193",
    },
    "cholesterol-2018": {
        "title": "2018 AHA/ACC/Multisociety Guideline on the Management of Blood Cholesterol",
        "url": "https://www.ahajournals.org/doi/10.1161/CIR.0000000000000625",
    },
    "hypertension-2017": {
        "title": "2017 ACC/AHA/AAPA/ABC/ACPM/AGS/APhA/ASH/ASPC/NMA/PCNA Guideline for the Prevention, Detection, Evaluation, and Management of High Blood Pressure in Adults",
        "url": "https://www.ahajournals.org/doi/10.1161/hyp.0000000000000065",
    },
    "primary-prevention-2019": {
        "title": "2019 ACC/AHA Guideline on the Primary Prevention of Cardiovascular Disease",
        "url": "https://www.ahajournals.org/doi/10.1161/CIR.0000000000000678",
    },
    "ckd-2024": {
        "title": "KDIGO 2024 Clinical Practice Guideline for the Evaluation and Management of Chronic Kidney Disease",
        "url": "https://doi.org/10.1016/j.kint.2023.10.018",
    },
    "ada-2025": {
        "title": "Standards of Care in Diabetes—2025 (American Diabetes Association)",
        "url": "https://diabetesjournals.org/care/issue/48/Supplement_1",
    },
    "acog-222": {
        "title": "Gestational Hypertension and Preeclampsia: ACOG Practice Bulletin, Number 222",
        "url": "https://doi.org/10.1097/AOG.0000000000003891",
    },
    "gold-2025": {
        "title": "Global Strategy for the Prevention, Diagnosis and Management of COPD: 2025 Report (GOLD)",
        "url": "https://goldcopd.org/2025-gold-report/",
    },
    "label": {
        "title": "FDA prescribing information (DailyMed) — drug-specific interactions and dose limits",
        "url": "https://dailymed.nlm.nih.gov/dailymed/",
    },
}


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


# Where a substance list ends. A sentence break, a contrast, a new actor — the
# actor cut is what keeps "allergic to aspirin and I take warfarin" from making
# "I take warfarin" an allergy — and a clause that carries a verb of its own,
# which is the commoner shape of the same mistake: "allergic to Aspirin and is a
# known hypertensive" used to record "is a known hypertensive" as an allergy and
# put that phrase in front of the clinician as the thing to avoid.
_ALLERGY_CLAUSE_BREAK = re.compile(
    r"\b(?:but|however|though|no other|nkda)\b|[.;\n]"
    r"|\b(?:and\s+)?(?:i|he|she|they|we|patient|the patient)\b"
    r"|\b(?:and\s+)?(?:is|are|was|were|has|have|had|takes?|taking|on|denies|"
    r"reports?|complains?|otherwise|noted)\b",
    re.I,
)


def extract_allergy_mentions(text: str) -> list[str]:
    """Allergy statements in a narrative — "allergic to aspirin and sulfa".

    Only explicit allergy wording matches, so "no known drug allergies"
    yields nothing (the pattern needs a substance after the keyword).
    """
    found: list[str] = []
    for match in _ALLERGY_PHRASE.finditer(str(text or "")):
        chunk = _ALLERGY_CLAUSE_BREAK.split(match.group(1))[0]
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
    # Two more risk-factor inputs the scores need: peripheral arterial disease
    # and a family history of coronary disease (HEART counts both).
    ("peripheral_arterial_disease",
     r"\b(?:peripheral arterial disease|peripheral vascular disease|\bpad\b|claudication|aortic plaque|\bpvd\b)\b"),
    ("family_history_cad",
     r"\b(?:family history of (?:heart|cad|coronary|cardiac)|father (?:had|died of)[^.;]{0,20}heart|mother (?:had|died of)[^.;]{0,20}heart|(?:dad|brother|sister) (?:had|died of)[^.;]{0,20}heart|sudden cardiac death in (?:the )?family)\b"),
    # Severe hypercholesterolaemia and statin intolerance are the two facts that
    # move lipid therapy past a statin; a history of pancreatitis is what makes a
    # triglyceride-lowering option worth offering at the severe end.
    ("familial_hypercholesterolemia",
     r"\b(?:familial hypercholesterola?emia|\bfh\b|genetic(?:ally)? high cholesterol|inherited high cholesterol)\b"),
    ("statin_intolerance",
     r"\b(?:statin intoleran\w*|intolerant to statins?|cannot tolerate statins?|statin[- ]associated muscle|statin[- ]induced myopathy)\b"),
    ("pancreatitis", r"\bpancreatitis\b"),
    ("angioedema", r"\bangl?ioedema\b|\bswelling of (?:the )?(?:tongue|lips|throat)\b"),
    ("refractory_angina",
     r"\b(?:refractory|intractable|persistent|ongoing) angina\b|\bangina (?:despite|on maximal|on full)\b"),
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
    non_hdl = _lab(labs, "non_hdl", "non_hdl_c")
    troponin = _lab(labs, "troponin", "troponin_i", "troponin_t", "troponin_flag")
    lvef = _lab(labs, "lvef", "ef")
    alt = _lab(labs, "alt", "sgpt")
    tg = _lab(labs, "triglycerides", "tg")
    uacr = _lab(labs, "uacr", "albumin_creatinine_ratio", "albuminuria")
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
    # LDL ≥190 mg/dL is severe hypercholesterolaemia: the band where a statin is
    # started and a non-statin agent is added rather than deferred, and where
    # familial hypercholesterolaemia is worked up.
    if ldl is not None and ldl >= 190:
        tags["ldl_very_high"] = ldl
    # Non-HDL-C is the same reading one threshold up: the international convention
    # puts its cut-off 30 mg/dL (0.8 mmol/L) above LDL-C's, so LDL-C's 160 is
    # non-HDL-C's 190 (ADR-022, ADR-023). A panel that prints only non-HDL raises
    # the lipid-lowering option through this tag, whether the number was printed
    # or derived from a printed total and HDL.
    if non_hdl is not None and non_hdl >= 190:
        tags["non_hdl_high"] = non_hdl
    if troponin is not None and troponin > 0.04:
        tags["troponin_elevated"] = troponin
    if lvef is not None and lvef < 40:
        tags["reduced_ef"] = lvef
    if alt is not None and alt > 120:
        tags["transaminitis"] = alt
    # Triglycerides split at the same 150/500 boundaries the report screen uses:
    # ≥150 is the level where an ASCVD patient has an indication for icosapent
    # ethyl, ≥500 is the level where pancreatitis risk makes fibrate therapy the
    # immediate question.
    if tg is not None:
        if tg >= 500:
            tags["triglycerides_severe"] = tg
        elif tg >= 150:
            tags["triglycerides_elevated"] = tg
    if uacr is not None and uacr >= 30:
        tags["albuminuria"] = uacr
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
        "source": ["acs-2025"],
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
        "source": ["acs-2025"],
    },
    {
        "key": "statin_high_intensity",
        "name": "High-intensity statin (atorvastatin/rosuvastatin)",
        "drug_class": "statin",
        "priority": 2,
        "indications": ["suspected_acs", "established_cad", "prior_mi", "prior_pci_cabg", "dyslipidemia", "dyslipidemia_lab", "non_hdl_high", "diabetes", "cerebrovascular_disease"],
        "avoid": [
            ("pregnancy", "absolute", "Statins are contraindicated in pregnancy and breastfeeding."),
            ("liver_disease", "relative", "Active hepatic disease — check transaminases before starting."),
            ("statin_intolerance", "relative", "Documented statin intolerance — review the reaction before rechallenging, and consider a different statin or a non-statin agent."),
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
        "source": ["cholesterol-2018", "ccd-2023"],
    },
    {
        "key": "statin_primary_prevention",
        "name": "Moderate-intensity statin (primary prevention)",
        "drug_class": "statin",
        "priority": 2,
        "indications": ["ascvd_intermediate_risk"],
        "avoid": [
            ("pregnancy", "absolute", "Statins are contraindicated in pregnancy and breastfeeding."),
            ("liver_disease", "relative", "Active hepatic disease — check transaminases before starting."),
            ("statin_intolerance", "relative", "Documented statin intolerance — review the reaction before rechallenging, and consider a different statin or a non-statin agent."),
        ],
        "caution": [
            ("diabetes", "Statin therapy can modestly raise glucose — in primary prevention the ten-year risk still decides."),
        ],
        "lab_guards": [("transaminitis", "relative", "ALT >3× upper limit — investigate before starting a statin.")],
        "allergens": ["statin", "statins", "atorvastatin", "rosuvastatin", "simvastatin", "pravastatin",
                      "lipitor", "crestor", "zocor"],
        "monitoring": ["Lipid panel at 6–8 weeks", "ALT if symptomatic", "Muscle symptoms (myopathy)"],
        "dose_note": "Atorvastatin 20–40 mg nightly, or rosuvastatin 10–20 mg — moderate intensity for primary prevention.",
        "evidence": "AHA/ACC cholesterol guideline — a statin is indicated when the ten-year ASCVD risk is intermediate (≥7.5%) or high, after a clinician-patient risk discussion.",
        "source": ["primary-prevention-2019", "cholesterol-2018"],
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
        "source": ["ccd-2023", "hf-2022"],
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
        "source": ["hf-2022", "ckd-2024"],
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
        "source": ["hf-2022"],
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
        "source": ["ccd-2023"],
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
        "source": ["hf-2022"],
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
        "source": ["hf-2022"],
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
        "source": ["hf-2022", "ada-2025"],
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
        "source": ["ccd-2023", "acs-2025"],
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
        "source": ["af-2023"],
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
        "source": ["ada-2025"],
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
        "source": ["ccd-2023", "label"],
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
        "source": ["af-2023"],
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
        "source": ["af-2023"],
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
        "monitoring": ["Blood pressure and renal function if one is unavoidable", "GI symptoms and bleeding signs"],
        "dose_note": "Avoid; use paracetamol for analgesia in this profile.",
        "evidence": "NSAIDs raise bleeding, renal and heart-failure risk in the flagged profiles below.",
        "source": ["ccd-2023", "label"],
    },
    {
        "key": "ticagrelor",
        "name": "Ticagrelor (P2Y12 inhibitor)",
        "drug_class": "p2y12",
        "priority": 2,
        "indications": ["suspected_acs", "prior_pci_cabg"],
        "avoid": [
            ("bleeding_risk", "absolute", "Active bleeding tendency — a P2Y12 inhibitor is unsafe without specialist review."),
            ("peptic_ulcer", "relative", "Recent GI bleed — only with gastroprotection and a defined duration."),
        ],
        "caution": [
            ("obstructive_airway_disease", "Ticagrelor commonly causes dyspnoea, which can be mistaken for bronchospasm — assess rather than assume."),
            ("bradyarrhythmia", "Bradycardia is a recognised effect — review the rate before adding it."),
        ],
        "lab_guards": [("thrombocytopenia", "relative", "Platelets <100 ×10⁹/L — bleeding risk on dual antiplatelet therapy.")],
        "allergens": ["ticagrelor", "brilinta", "p2y12", "prasugrel", "effient"],
        "monitoring": ["Bleeding signs", "Dyspnoea", "Adherence/duration per stent protocol"],
        "dose_note": "180 mg loading dose then 90 mg twice daily for 12 months post-ACS; 60 mg twice daily beyond 12 months where the protocol continues it.",
        "evidence": "ACS guideline — ticagrelor is a preferred P2Y12 inhibitor in ACS regardless of the planned invasive strategy, and with aspirin after PCI.",
        "source": ["acs-2025"],
    },
    {
        "key": "arni",
        "name": "ARNI (sacubitril/valsartan)",
        "drug_class": "arni",
        "priority": 3,
        "indications": ["heart_failure", "reduced_ef"],
        "avoid": [
            ("pregnancy", "absolute", "ARNI is contraindicated in pregnancy — stop before conception."),
            ("angioedema", "absolute", "Prior angioedema on a RAAS agent — ARNI is contraindicated; specialist review."),
            ("hyperkalemia", "absolute", "Do not start with K+ >5.5 mmol/L — correct potassium first."),
        ],
        "caution": [
            ("chronic_kidney_disease", "Expect a small creatinine rise; recheck at 1–2 weeks."),
            ("borderline_hyperkalemia", "K+ 5.0–5.5 mmol/L — recheck potassium and creatinine after 1 week."),
        ],
        "lab_guards": [("renal_severe", "relative", "eGFR <30 mL/min — start at the lowest dose with close follow-up.")],
        "allergens": ["sacubitril", "entresto", "arni", "valsartan", "arb"],
        "monitoring": ["Blood pressure", "Potassium and creatinine at 1–2 weeks", "Angioedema", "Symptoms and NYHA class"],
        "dose_note": "Sacubitril/valsartan 49/51 mg twice daily, titrated to 97/103 mg; start at 24/26 mg if RAAS-naive or renally impaired. Wait 36 h after the last ACE inhibitor.",
        "evidence": "Heart-failure guideline — ARNI is preferred over an ACE inhibitor or ARB in symptomatic HFrEF (NYHA II–III) to reduce mortality and hospitalisation.",
        "source": ["hf-2022"],
    },
    {
        "key": "ivabradine",
        "name": "Ivabradine",
        "drug_class": "sinus_node_inhibitor",
        "priority": 5,
        "indications": ["heart_failure", "reduced_ef"],
        "avoid": [
            ("atrial_fibrillation", "absolute", "Ivabradine acts on the sinus node and does not control rate in atrial fibrillation."),
            ("bradyarrhythmia", "absolute", "Bradycardia, sick sinus syndrome or heart block without a pacemaker."),
        ],
        "caution": [
            ("hypotension", "Review blood pressure before titrating; both effects are additive."),
            ("liver_disease", "Hepatic impairment raises exposure — use the lower dose."),
        ],
        "lab_guards": [],
        "allergens": ["ivabradine", "corlanor", "procoralan"],
        "monitoring": ["Resting heart rate", "Visual phosphenes", "Blood pressure"],
        "dose_note": "5 mg twice daily, titrated to 7.5 mg twice daily after 2 weeks if resting HR is still ≥60 bpm.",
        "evidence": "Heart-failure guideline — ivabradine for symptomatic HFrEF in sinus rhythm with HR ≥70 bpm on maximally tolerated beta-blockade; CCS guideline for angina when beta-blockers are contraindicated.",
        "source": ["hf-2022", "ccd-2023"],
    },
    {
        "key": "hydralazine_isosorbide",
        "name": "Hydralazine with isosorbide dinitrate",
        "drug_class": "vasodilator",
        "priority": 6,
        "indications": ["heart_failure", "reduced_ef"],
        "avoid": [
            ("aortic_stenosis", "relative", "Severe aortic stenosis — vasodilatation can cause syncope; specialist review."),
            ("angioedema", "relative", "Prior angioedema on a vasodilator — review the reaction before using a nitrate-containing combination."),
        ],
        "caution": [
            ("hypotension", "Review blood pressure before each titration; the combination is a potent vasodilator."),
            ("chronic_kidney_disease", "Renal impairment raises hydralazine exposure — start low and titrate slowly."),
        ],
        "lab_guards": [],
        "allergens": ["hydralazine", "isosorbide", "isosorbide dinitrate", "bidil", "nitrate", "nitrates"],
        "monitoring": ["Blood pressure and heart rate", "Headache (expected with nitrates)", "Lupus-like symptoms (hydralazine)", "Adherence (three times daily)"],
        "dose_note": "Hydralazine 37.5 mg with isosorbide dinitrate 20 mg three times daily, titrated to the maximum tolerated dose.",
        "evidence": "Heart-failure guideline — the hydralazine/isosorbide dinitrate combination is useful in HFrEF where RAAS blockade is limited by renal function or potassium, and in self-identified Black patients already on guideline-directed therapy.",
        "source": ["hf-2022"],
    },
    {
        "key": "finerenone",
        "name": "Finerenone (non-steroidal MRA)",
        "drug_class": "nonsteroidal_mra",
        "priority": 4,
        # Diabetes *with* albuminuria: the trial population, and not every CKD
        # patient with diabetes. A compound indication keeps the two facts
        # together instead of OR-ing them.
        "indications": ["diabetic_kidney_disease"],
        "avoid": [
            ("hyperkalemia", "absolute", "K+ >5.5 mmol/L — correct potassium before starting."),
            ("renal_severe", "absolute", "eGFR <25 mL/min — finerenone is not initiated at this level."),
        ],
        "caution": [
            ("borderline_hyperkalemia", "K+ 5.0–5.5 mmol/L — recheck potassium at 4 weeks and dose-reduce if it rises."),
            ("chronic_kidney_disease", "Dose is set by eGFR; recheck eGFR at 4 weeks and then periodically."),
        ],
        "lab_guards": [("renal_severe", "absolute", "eGFR <25 mL/min — do not start finerenone.")],
        "allergens": ["finerenone", "kerendia", "mra"],
        "monitoring": ["Potassium and eGFR at 4 weeks, then periodically", "Blood pressure", "Genital infections"],
        "dose_note": "10 mg daily when eGFR 25–60 mL/min, 20 mg daily when eGFR ≥60; titrate on potassium.",
        "evidence": "KDIGO CKD guideline — non-steroidal MRA for type 2 diabetes with CKD and albuminuria (UACR ≥30 mg/g) already on maximal tolerated RAAS blockade.",
        "source": ["ckd-2024", "ada-2025"],
    },
    {
        "key": "thiazide",
        "name": "Thiazide-like diuretic (chlorthalidone/indapamide)",
        "drug_class": "thiazide",
        "priority": 6,
        "indications": ["hypertension"],
        "avoid": [],
        "caution": [
            ("gout", "Thiazides raise urate — review gout control and consider an alternative."),
            ("hyponatremia", "Sodium <130 mmol/L — investigate and avoid aggressive diuresis."),
            ("hypokalemia", "K+ <3.5 mmol/L — replace potassium before starting."),
        ],
        "lab_guards": [("hyponatremia", "relative", "Sodium <130 mmol/L — review the diuretic choice before starting.")],
        # Sulfonamide cross-reactivity with thiazides is uncommon and poorly
        # supported, so a sulfa allergy is a review flag here, not a block.
        "allergens": ["thiazide", "thiazides", "hydrochlorothiazide", "hctz", "chlorthalidone", "indapamide"],
        "allergen_soft": ["sulfa", "sulfonamide", "sulfonamides", "sulfa drugs"],
        "monitoring": ["Sodium and potassium at 2–4 weeks", "Urate if gout", "Blood pressure"],
        "dose_note": "Chlorthalidone 12.5–25 mg daily, or indapamide 1.25–2.5 mg daily.",
        "evidence": "Hypertension guideline — a thiazide-type diuretic is a first-line agent for hypertension, alone or as add-on therapy.",
        "source": ["hypertension-2017"],
    },
    {
        "key": "ezetimibe",
        "name": "Ezetimibe",
        "drug_class": "cholesterol_absorption_inhibitor",
        "priority": 4,
        "indications": ["dyslipidemia", "dyslipidemia_lab", "non_hdl_high", "ldl_very_high", "statin_intolerance", "established_cad", "prior_mi"],
        "avoid": [
            ("pregnancy", "relative", "Not recommended in pregnancy or breastfeeding — stop before conception and plan lipid therapy with the prescriber."),
            ("liver_disease", "relative", "Active hepatic disease — check transaminases before adding it to a statin."),
        ],
        "caution": [("transaminitis", "ALT >3× upper limit — investigate before adding another lipid-lowering agent.")],
        "lab_guards": [("transaminitis", "relative", "ALT >3× upper limit — investigate before starting.")],
        "allergens": ["ezetimibe", "zetia", "ezetrol"],
        "monitoring": ["Lipid panel at 4–12 weeks", "ALT when combined with a statin", "Muscle symptoms if a statin is co-prescribed"],
        "dose_note": "Ezetimibe 10 mg once daily, with or without a statin.",
        "evidence": "Cholesterol guideline — ezetimibe is added to maximally tolerated statin therapy when LDL-C remains above the treatment threshold, and is an option when a statin cannot be used.",
        "source": ["cholesterol-2018"],
    },
    {
        "key": "pcsk9_inhibitor",
        "name": "PCSK9 inhibitor (evolocumab/alirocumab)",
        "drug_class": "pcsk9_inhibitor",
        "priority": 5,
        "indications": ["familial_hypercholesterolemia", "ldl_very_high", "statin_intolerance"],
        "avoid": [
            ("pregnancy", "relative", "Not recommended in pregnancy — specialist lipid planning before conception."),
        ],
        "caution": [("liver_disease", "No dose adjustment is established; review hepatic disease with the prescriber.")],
        "lab_guards": [],
        "allergens": ["evolocumab", "alirocumab", "repatha", "praluent", "pcsk9"],
        "monitoring": ["Lipid panel at 4–12 weeks", "Injection-site reactions", "Adherence to the injection schedule"],
        "dose_note": "Evolocumab 140 mg every 2 weeks or 420 mg monthly; alirocumab 75–150 mg every 2 weeks.",
        "evidence": "Cholesterol guideline — a PCSK9 inhibitor for familial hypercholesterolaemia or severe LDL-C elevation when LDL-C stays above threshold on a maximally tolerated statin plus ezetimibe.",
        "source": ["cholesterol-2018"],
    },
    {
        "key": "icosapent_ethyl",
        "name": "Icosapent ethyl (purified EPA)",
        "drug_class": "omega3",
        "priority": 5,
        "indications": ["residual_hypertriglyceridaemia"],
        "avoid": [
            ("bleeding_risk", "relative", "Bleeding tendency — high-dose EPA adds to antiplatelet/anticoagulant bleeding."),
        ],
        "caution": [
            ("atrial_fibrillation", "Trial data show a higher incidence of atrial fibrillation — review rate and rhythm at follow-up."),
            ("liver_disease", "Review hepatic disease before starting; monitor ALT."),
        ],
        "lab_guards": [("thrombocytopenia", "relative", "Platelets <100 ×10⁹/L — review bleeding risk before adding 2 g twice daily.")],
        "allergens": ["icosapent", "vascepa", "epa", "omega-3", "omega 3", "fish oil"],
        "allergen_soft": ["fish", "shellfish"],
        "monitoring": ["Triglycerides at 4–12 weeks", "ALT", "Bleeding signs", "Atrial fibrillation"],
        "dose_note": "Icosapent ethyl 2 g twice daily with food, on top of a statin.",
        "evidence": "Chronic coronary disease guideline — icosapent ethyl for patients with ASCVD or diabetes and residual hypertriglyceridaemia (150–499 mg/dL) despite statin therapy.",
        "source": ["ccd-2023"],
    },
    {
        "key": "fenofibrate",
        "name": "Fenofibrate",
        "drug_class": "fibrate",
        "priority": 6,
        "indications": ["triglycerides_severe", "pancreatitis"],
        "avoid": [
            ("liver_disease", "relative", "Active hepatic or biliary disease — fibrates are contraindicated in significant liver disease."),
            ("renal_severe", "relative", "eGFR <30 mL/min — dose-reduce substantially and review the indication."),
        ],
        "caution": [
            ("chronic_kidney_disease", "Dose is set by eGFR; recheck creatinine at 4 weeks."),
            ("diabetes", "Fibrates can modestly raise creatinine — interpret the renal trend with that in mind."),
        ],
        "lab_guards": [("renal_severe", "relative", "eGFR <30 mL/min — start at the lowest dose or choose another agent.")],
        "allergens": ["fenofibrate", "tricor", "lipanthyl", "fibrate", "fibrates"],
        "monitoring": ["Triglycerides and ALT at 8–12 weeks", "Creatinine", "Muscle symptoms if combined with a statin"],
        "dose_note": "Fenofibrate 145 mg daily (micronized 48–145 mg); reduce in renal impairment.",
        "evidence": "Cholesterol guideline — a fibrate for severe hypertriglyceridaemia (≥500 mg/dL) to reduce pancreatitis risk, after secondary causes are addressed.",
        "source": ["cholesterol-2018"],
    },
    {
        "key": "colchicine",
        "name": "Colchicine (low dose)",
        "drug_class": "anti_inflammatory",
        "priority": 6,
        "indications": ["established_cad", "prior_mi"],
        "avoid": [
            ("renal_severe", "relative", "eGFR <30 mL/min — dose must be halved and reviewed; toxicity rises steeply."),
            ("liver_disease", "relative", "Hepatic impairment — colchicine clearance falls; specialist review."),
        ],
        "caution": [
            ("chronic_kidney_disease", "Dose by eGFR; recheck renal function and blood counts at review."),
            ("bleeding_risk", "Colchicine can cause marrow suppression — check the blood count if bruising appears."),
        ],
        "lab_guards": [("renal_severe", "relative", "eGFR <30 mL/min — reduce the dose and review before starting.")],
        "allergens": ["colchicine", "colcrys", "mitigare"],
        "monitoring": ["Gastrointestinal tolerance", "Blood count", "CK if muscle symptoms", "Renal function"],
        "dose_note": "Colchicine 0.5 mg once daily; 0.5 mg on alternate days if eGFR <30 or on a CYP3A4/P-gp inhibitor.",
        "evidence": "Chronic coronary disease guideline — low-dose colchicine (0.5 mg daily) may be considered for secondary prevention of atherosclerotic events.",
        "source": ["ccd-2023"],
    },
    {
        "key": "ranolazine",
        "name": "Ranolazine",
        "drug_class": "antianginal",
        "priority": 6,
        "indications": ["refractory_angina"],
        "avoid": [
            ("liver_disease", "absolute", "Cirrhosis — ranolazine is contraindicated in significant hepatic impairment."),
            ("bradyarrhythmia", "relative", "QT prolongation risk — review the ECG and rate before starting."),
        ],
        "caution": [
            ("chronic_kidney_disease", "Dose is limited in renal impairment; review QTc."),
            ("hypokalemia", "Correct potassium before starting — hypokalaemia adds to QT risk."),
        ],
        "lab_guards": [],
        "allergens": ["ranolazine", "ranexa"],
        "monitoring": ["ECG/QTc at baseline and after titration", "Blood pressure", "Dizziness"],
        "dose_note": "Ranolazine 375–500 mg twice daily, titrated to a maximum of 1000 mg twice daily.",
        "evidence": "Chronic coronary disease guideline — ranolazine for refractory angina when other antianginal therapy is insufficient or not tolerated.",
        "source": ["ccd-2023"],
    },
    {
        "key": "dronedarone",
        "name": "Dronedarone",
        "drug_class": "antiarrhythmic",
        "priority": 7,
        "indications": ["atrial_fibrillation", "atrial_fibrillation_symptomatic"],
        "avoid": [
            ("heart_failure", "absolute", "Dronedarone is contraindicated in symptomatic heart failure or recent decompensation — mortality rose in that population."),
            ("reduced_ef", "absolute", "LVEF <40% — do not use dronedarone."),
            ("bradyarrhythmia", "relative", "Bradycardia or AV block — review rate and conduction before starting."),
        ],
        "caution": [
            ("liver_disease", "Hepatic injury is a recognised effect — check LFTs before and during therapy."),
            ("chronic_kidney_disease", "Renal impairment raises exposure; review the dose and creatinine."),
        ],
        "lab_guards": [],
        "allergens": ["dronedarone", "multaq"],
        "monitoring": ["ECG (rate and QTc)", "Liver function tests", "Creatinine", "Symptoms of heart failure"],
        "dose_note": "Dronedarone 400 mg twice daily with meals.",
        "evidence": "Atrial fibrillation guideline — dronedarone to maintain sinus rhythm in paroxysmal or persistent AF without LV dysfunction; not for permanent AF.",
        "source": ["af-2023"],
    },
    {
        "key": "flecainide",
        "name": "Flecainide",
        "drug_class": "antiarrhythmic",
        "priority": 8,
        "indications": ["atrial_fibrillation_symptomatic"],
        "avoid": [
            ("established_cad", "absolute", "Flecainide is contraindicated in ischaemic heart disease — proarrhythmic risk."),
            ("prior_mi", "absolute", "Prior myocardial infarction — do not use flecainide."),
            ("heart_failure", "absolute", "Structural heart disease with heart failure — contraindicated."),
            ("reduced_ef", "absolute", "LVEF <40% — do not use flecainide."),
            ("bradyarrhythmia", "relative", "Conduction disease — review the ECG before starting."),
        ],
        "caution": [
            ("chronic_kidney_disease", "Renal impairment raises exposure — start low and review the ECG."),
            ("liver_disease", "Hepatic impairment raises exposure — reduce the dose."),
        ],
        "lab_guards": [],
        "allergens": ["flecainide", "tambocor", "flecaine"],
        "monitoring": ["ECG (QRS width) at baseline and after titration", "Rate control during episodes", "Exercise testing if ischaemia is possible"],
        "dose_note": "Flecainide 50–150 mg twice daily (maximum 300 mg/day), with a rate-control agent.",
        "evidence": "Atrial fibrillation guideline — flecainide for rhythm control in AF without structural or ischaemic heart disease; contraindicated when either is present.",
        "source": ["af-2023"],
    },
    {
        "key": "nd_ccb",
        "name": "Non-dihydropyridine CCB (diltiazem/verapamil)",
        "drug_class": "nd_ccb",
        "priority": 4,
        "indications": ["atrial_fibrillation", "atrial_fibrillation_symptomatic", "hypertension"],
        "avoid": [
            ("heart_failure", "absolute", "Diltiazem/verapamil are negative inotropes — do not use in heart failure with reduced ejection fraction."),
            ("reduced_ef", "absolute", "LVEF <40% — use a beta-blocker or another rate-control strategy."),
            ("bradyarrhythmia", "relative", "Bradycardia or AV block — review conduction before starting."),
            ("pregnancy", "relative", "Diltiazem/verapamil are not first-line in pregnancy — nifedipine or labetalol are preferred."),
        ],
        "caution": [
            ("aortic_stenosis", "Vasodilatation and negative inotropy — specialist review in severe aortic stenosis."),
            ("hypertension", "Monitor blood pressure during titration; both agents cause vasodilatation."),
        ],
        "lab_guards": [],
        "allergens": ["diltiazem", "verapamil", "isoptin", "dilzem", "calcium channel blocker", "ccb"],
        "monitoring": ["Heart rate and blood pressure", "ECG for conduction delay", "Ankle oedema"],
        "dose_note": "Diltiazem 120–360 mg daily (extended release) or verapamil 80–120 mg three times daily.",
        "evidence": "Atrial fibrillation guideline — a non-dihydropyridine calcium-channel blocker for rate control when a beta-blocker is contraindicated or insufficient, and not in HFrEF.",
        "source": ["af-2023", "hypertension-2017"],
    },
    {
        "key": "labetalol",
        "name": "Labetalol (pregnancy hypertension)",
        "drug_class": "beta_blocker",
        "priority": 3,
        "indications": ["pregnancy_hypertension"],
        "avoid": [
            ("obstructive_airway_disease", "relative", "Asthma — a cardioselective agent or an alternative class is preferred; review for bronchospasm."),
            ("bradyarrhythmia", "relative", "Bradycardia or heart block — review conduction before starting."),
            ("heart_failure", "relative", "Start low and titrate slowly; avoid during acute decompensation."),
        ],
        "caution": [
            ("diabetes", "Beta-blockade can mask hypoglycaemia awareness — counsel the patient."),
            ("asthma", "Review airway disease before titration."),
        ],
        "lab_guards": [],
        "allergens": ["labetalol", "trandate", "normodyne", "beta blocker", "beta-blocker"],
        "monitoring": ["Blood pressure and heart rate", "Fetal growth in pregnancy", "Symptoms of bronchospasm"],
        "dose_note": "Labetalol 100 mg twice daily, titrated to 400 mg twice daily (maximum 2400 mg/day).",
        "evidence": "ACOG practice bulletin — labetalol is a first-line agent for chronic and severe hypertension in pregnancy; the hypertension guideline covers its use outside pregnancy.",
        "source": ["acog-222", "hypertension-2017"],
    },
    {
        "key": "glp1_ra",
        "name": "GLP-1 receptor agonist (semaglutide/dulaglutide)",
        "drug_class": "glp1_ra",
        "priority": 5,
        "indications": ["diabetes", "obesity", "diabetes_with_ascvd"],
        "avoid": [
            ("pregnancy", "absolute", "GLP-1 receptor agonists are contraindicated in pregnancy and not for use while breastfeeding."),
            ("pancreatitis", "relative", "Previous pancreatitis — weigh the recurrence risk before starting."),
        ],
        "caution": [
            ("diabetes", "Review insulin and sulfonylurea doses when starting, to avoid hypoglycaemia."),
            ("chronic_kidney_disease", "Gastrointestinal losses can dehydrate — review renal function during titration."),
        ],
        "lab_guards": [],
        "allergens": ["semaglutide", "ozempic", "wegovy", "rybelsus", "dulaglutide", "trulicity", "liraglutide", "victoza", "glp-1", "glp1"],
        "monitoring": ["Weight and HbA1c", "Gastrointestinal tolerance", "Pancreatitis symptoms", "Renal function during titration"],
        "dose_note": "Semaglutide 0.25 mg weekly for 4 weeks, then 0.5 mg, titrated to 1–2 mg weekly (oral semaglutide 3–14 mg daily).",
        "evidence": "Diabetes standards of care — a GLP-1 receptor agonist with proven cardiovascular benefit for type 2 diabetes with ASCVD or high cardiovascular risk, independent of HbA1c; the coronary-disease guideline makes the same recommendation.",
        "source": ["ada-2025", "ccd-2023"],
    },
    {
        "key": "bempedoic_acid",
        "name": "Bempedoic acid",
        "drug_class": "acl_inhibitor",
        "priority": 6,
        "indications": ["statin_intolerance", "ldl_very_high"],
        "avoid": [
            ("pregnancy", "relative", "Not recommended in pregnancy — plan lipid therapy before conception."),
            ("liver_disease", "relative", "Active hepatic disease — check transaminases before starting."),
        ],
        "caution": [
            ("gout", "Bempedoic acid raises urate — review gout control and monitor."),
            ("transaminitis", "ALT >3× upper limit — investigate before starting."),
        ],
        "lab_guards": [("transaminitis", "relative", "ALT >3× upper limit — investigate before starting.")],
        "allergens": ["bempedoic", "nexletol", "nexlizet"],
        "monitoring": ["Lipid panel at 4–12 weeks", "Urate if gout", "ALT", "Tendon pain"],
        "dose_note": "Bempedoic acid 180 mg once daily, with or without ezetimibe.",
        "evidence": "FDA prescribing information — bempedoic acid lowers LDL-C in statin-intolerant patients and in heterozygous familial hypercholesterolaemia, added to other lipid-lowering therapy.",
        "source": ["label"],
    },
]

_DRUG_BY_KEY = {d["key"]: d for d in DRUGS}
_CLASS_OF = {d["key"]: d["drug_class"] for d in DRUGS}
_KEY_BY_NAME = {d["name"]: d["key"] for d in DRUGS}

# Current-medication aliases (incl. common brands) → internal drug key.
# Used for interaction screening and "already documented" detection.
MED_ALIASES: dict[str, tuple[str, ...]] = {
    "aspirin": ("aspirin", "asa", "acetylsalicylic", "disprin", "ecosprin", "aspilet", "aspin", "salicylate"),
    # Ticagrelor is its own entry now, so it is not an alias of clopidogrel:
    # a patient on it should not be reported as being on the other P2Y12 agent.
    "clopidogrel": ("clopidogrel", "plavix", "prasugrel", "effient"),
    "ticagrelor": ("ticagrelor", "brilinta"),
    "arni": ("sacubitril", "entresto", "sacubitril/valsartan", "sacubitril valsartan", "arni"),
    "ivabradine": ("ivabradine", "corlanor", "procoralan"),
    "hydralazine_isosorbide": ("hydralazine", "isosorbide dinitrate", "isosorbide", "bidil", "apresoline"),
    "finerenone": ("finerenone", "kerendia"),
    "thiazide": ("hydrochlorothiazide", "hctz", "chlorthalidone", "indapamide", "bendroflumethiazide", "thiazide"),
    "ezetimibe": ("ezetimibe", "zetia", "ezetrol"),
    "pcsk9_inhibitor": ("evolocumab", "repatha", "alirocumab", "praluent", "pcsk9"),
    "icosapent_ethyl": ("icosapent", "vascepa", "epa", "omega-3", "omega 3", "fish oil"),
    "fenofibrate": ("fenofibrate", "tricor", "lipanthyl", "fibrate"),
    "colchicine": ("colchicine", "colcrys", "mitigare"),
    "ranolazine": ("ranolazine", "ranexa"),
    "dronedarone": ("dronedarone", "multaq"),
    "flecainide": ("flecainide", "tambocor", "flecaine"),
    "labetalol": ("labetalol", "trandate", "normodyne"),
    "glp1_ra": ("semaglutide", "ozempic", "wegovy", "rybelsus", "dulaglutide", "trulicity", "liraglutide", "victoza", "glp-1", "glp1"),
    "bempedoic_acid": ("bempedoic", "nexletol", "nexlizet"),
    "statin_high_intensity": ("atorvastatin", "rosuvastatin", "simvastatin", "pravastatin", "statin", "lipitor", "crestor", "zocor"),
    "beta_blocker": ("metoprolol", "bisoprolol", "carvedilol", "atenolol", "nebivolol", "propranolol", "lopressor", "betaloc", "concor"),
    "ace_inhibitor": ("ramipril", "lisinopril", "enalapril", "captopril", "perindopril", "trandolapril", "ace inhibitor", "acei"),
    "arb": ("losartan", "valsartan", "irbesartan", "candesartan", "telmisartan", "olmesartan", "arb"),
    # Diltiazem and verapamil are non-dihydropyridines with their own entry; a
    # patient on one of them must not also be reported as being on amlodipine.
    "ccb": ("amlodipine", "nifedipine", "lercanidipine", "norvasc", "calcium channel blocker"),
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
    "statin_primary_prevention": "Do not rechallenge a true statin allergy: consider a different statin only after reviewing the reaction, or a non-statin lipid-lowering option with specialist input.",
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
    "ticagrelor": "If a P2Y12 inhibitor is essential (post-PCI), clopidogrel is the usual alternative — specialist input required.",
    "arni": "An ACE inhibitor or ARB is the alternative RAAS strategy if ARNI is not tolerated; recheck potassium and renal function.",
    "ivabradine": "Rate control needs another route: beta-blocker, digoxin or specialist rhythm input.",
    "hydralazine_isosorbide": "If a nitrate or hydralazine allergy is confirmed, other vasodilators need specialist input — do not rechallenge.",
    "finerenone": "Other potassium-sparing options are limited; discuss with the prescriber and recheck potassium before any substitute.",
    "thiazide": "A calcium-channel blocker or an ACE inhibitor/ARB is the usual alternative antihypertensive — avoid other sulfonamide diuretics if the reaction was a true allergy.",
    "ezetimibe": "A PCSK9 inhibitor or bempedoic acid is the non-statin alternative; reviewer input is needed on the reaction history.",
    "pcsk9_inhibitor": "Ezetimibe or bempedoic acid is the non-injectable alternative — do not rechallenge an injection reaction without review.",
    "icosapent_ethyl": "A fibrate is the usual alternative for severe hypertriglyceridaemia; review the reaction before any omega-3 product.",
    "fenofibrate": "Icosapent ethyl or a statin-first strategy is the alternative; do not substitute another fibrate without review.",
    "colchicine": "Do not substitute another colchicine preparation; the anti-inflammatory option needs prescriber review.",
    "ranolazine": "Angina control needs another route: beta-blocker, calcium-channel blocker or nitrate, with the same review.",
    "dronedarone": "Rhythm control needs specialist input — another antiarrhythmic, or catheter ablation, rather than a substitute here.",
    "flecainide": "Rhythm control needs specialist input — a different antiarrhythmic or ablation; do not substitute another sodium-channel blocker.",
    "nd_ccb": "If diltiazem/verapamil cannot be used, a beta-blocker (outside HFrEF) or digoxin is the rate-control alternative.",
    "labetalol": "Nifedipine or methyldopa are the other pregnancy-safe antihypertensives; do not substitute a RAAS agent in pregnancy.",
    "glp1_ra": "Another glucose-lowering agent with cardiovascular benefit may be considered — an SGLT2 inhibitor where it is indicated.",
    "bempedoic_acid": "Ezetimibe or a PCSK9 inhibitor is the alternative non-statin route; review the reaction before substituting.",
}


# ---------------------------------------------------------------------------
# Interaction table (drug key or drug class on either side)
# ---------------------------------------------------------------------------

INTERACTIONS: list[dict[str, str]] = [
    {"a": "p2y12", "b": "anticoagulant", "severity": "major",
     "note": "P2Y12 inhibitor plus anticoagulant markedly increases bleeding (and the risk compounds with aspirin).",
     "action": "Use only with a defined indication and stop date; add gastroprotection and review at each visit.",
     "source": ["acs-2025", "af-2023"]},
    {"a": "aspirin", "b": "anticoagulant", "severity": "major",
     "note": "Antiplatelet plus anticoagulant roughly doubles major bleeding.",
     "action": "Combine only with a clear indication (e.g. recent stent); add gastroprotection and set a stop date.",
     "source": ["af-2023"]},
    {"a": "aspirin", "b": "p2y12", "severity": "major",
     "note": "Dual antiplatelet therapy raises bleeding without benefit outside ACS/PCI.",
     "action": "Use only per ACS/PCI protocol, and document the planned duration.",
     "source": ["acs-2025"]},
    {"a": "aspirin", "b": "nsaid", "severity": "major",
     "note": "NSAID plus antiplatelet increases GI bleeding and renal risk.",
     "action": "Avoid NSAIDs; use paracetamol for analgesia.",
     "source": ["ccd-2023", "label"]},
    {"a": "nsaid", "b": "anticoagulant", "severity": "major",
     "note": "NSAID plus anticoagulant substantially increases GI and intracranial bleeding.",
     "action": "Avoid NSAIDs; if unavoidable add gastroprotection (generally not recommended).",
     "source": ["label", "af-2023"]},
    {"a": "nsaid", "b": "ace_inhibitor", "severity": "moderate",
     "note": "NSAIDs blunt antihypertensive effect and can worsen renal function.",
     "action": "Avoid where possible; if used, check creatinine and potassium within a week.",
     "source": ["ckd-2024"]},
    {"a": "nsaid", "b": "arb", "severity": "moderate",
     "note": "NSAIDs blunt ARB effect and can worsen renal function.",
     "action": "Avoid where possible; monitor renal function if used.",
     "source": ["ckd-2024"]},
    {"a": "nsaid", "b": "loop_diuretic", "severity": "moderate",
     "note": "NSAIDs reduce diuretic efficacy ('triple whammy' with a RAAS blocker).",
     "action": "Avoid; review diuretic dose if NSAIDs are unavoidable.",
     "source": ["label", "hf-2022"]},
    {"a": "ace_inhibitor", "b": "mra", "severity": "major",
     "note": "RAAS blocker plus MRA increases hyperkalaemia risk.",
     "action": "Check potassium and creatinine at 1 and 4 weeks; stop if K+ >5.5 mmol/L.",
     "source": ["hf-2022", "ckd-2024"]},
    {"a": "arb", "b": "mra", "severity": "major",
     "note": "RAAS blocker plus MRA increases hyperkalaemia risk.",
     "action": "Check potassium and creatinine at 1 and 4 weeks.",
     "source": ["hf-2022"]},
    {"a": "ace_inhibitor", "b": "arb", "severity": "major",
     "note": "Dual RAAS blockade adds hyperkalaemia and renal injury without outcome benefit.",
     "action": "Use one agent only.",
     "source": ["hf-2022"]},
    {"a": "beta_blocker", "b": "nd_ccb", "severity": "major",
     "note": "Beta-blocker plus verapamil/diltiazem causes bradycardia, heart block and hypotension.",
     "action": "Avoid the combination; amlodipine is the safe calcium-channel option here.",
     "source": ["label", "af-2023"]},
    {"a": "statin_high_intensity", "b": "amiodarone", "severity": "major",
     "note": "Amiodarone raises simvastatin/atorvastatin exposure — myopathy/rhabdomyolysis risk.",
     "action": "Cap simvastatin at 20 mg, or switch to rosuvastatin/pravastatin and warn about muscle pain.",
     "source": ["label"]},
    {"a": "amiodarone", "b": "anticoagulant", "severity": "major",
     "note": "Amiodarone raises warfarin INR and DOAC exposure (P-gp inhibition).",
     "action": "Reduce the anticoagulant dose and monitor INR/bleeding closely.",
     "source": ["label"]},
    {"a": "amiodarone", "b": "digoxin", "severity": "major",
     "note": "Amiodarone approximately doubles digoxin levels.",
     "action": "Halve the digoxin dose and check the level.",
     "source": ["label"]},
    {"a": "digoxin", "b": "loop_diuretic", "severity": "moderate",
     "note": "Diuretic-induced hypokalaemia potentiates digoxin toxicity.",
     "action": "Monitor potassium and digoxin level; replace potassium as needed.",
     "source": ["label", "hf-2022"]},
    {"a": "nitrate", "b": "pde5_inhibitor", "severity": "major",
     "note": "Nitrate plus a PDE5 inhibitor (sildenafil/tadalafil) causes profound hypotension.",
     "action": "Contraindicated — separate by at least 24 h (48 h for tadalafil) and counsel the patient.",
     "source": ["label", "ccd-2023"]},
    {"a": "clopidogrel", "b": "ppi", "severity": "moderate",
     "note": "Omeprazole (not pantoprazole) reduces clopidogrel activation via CYP2C19.",
     "action": "Use pantoprazole when gastroprotection is needed alongside clopidogrel.",
     "source": ["label", "ccd-2023"]},
    {"a": "metformin", "b": "loop_diuretic", "severity": "moderate",
     "note": "Diuretic-induced volume depletion raises the risk of metformin-associated lactic acidosis.",
     "action": "Hold metformin during acute illness or aggressive diuresis.",
     "source": ["ada-2025", "label"]},
    {"a": "arni", "b": "ace_inhibitor", "severity": "major",
     "note": "An ARNI and an ACE inhibitor together cause angioedema and dual RAAS blockade with no added benefit.",
     "action": "Never combine them: stop the ACE inhibitor and wait 36 hours before the first ARNI dose.",
     "source": ["hf-2022", "label"]},
    {"a": "arni", "b": "arb", "severity": "major",
     "note": "The ARB component of an ARNI already blocks the receptor — stacking another ARB is dual RAAS blockade.",
     "action": "Use one RAAS strategy only; the ARNI replaces the ARB.",
     "source": ["hf-2022"]},
    {"a": "arni", "b": "mra", "severity": "major",
     "note": "ARNI plus an MRA raises the risk of hyperkalaemia and renal injury.",
     "action": "Check potassium and creatinine at 1 and 4 weeks; stop if K+ >5.5 mmol/L.",
     "source": ["hf-2022"]},
    {"a": "ivabradine", "b": "nd_ccb", "severity": "major",
     "note": "Verapamil/diltiazem inhibit CYP3A4 and raise ivabradine exposure, adding bradycardia to their own negative chronotropy.",
     "action": "Avoid the combination; if rate control is the goal, choose one agent.",
     "source": ["label"]},
    {"a": "ivabradine", "b": "beta_blocker", "severity": "moderate",
     "note": "Both slow the sinus node — the combination is used deliberately in HFrEF but needs a rate check.",
     "action": "Titrate against resting heart rate and review for symptomatic bradycardia.",
     "source": ["hf-2022"]},
    {"a": "colchicine", "b": "statin", "severity": "major",
     "note": "Colchicine plus a statin raises the risk of myopathy and rhabdomyolysis.",
     "action": "Warn about muscle pain; check CK if symptoms appear, and reduce the colchicine dose in renal impairment.",
     "source": ["label"]},
    {"a": "colchicine", "b": "nd_ccb", "severity": "major",
     "note": "Diltiazem/verapamil inhibit CYP3A4 and P-gp, sharply raising colchicine levels and toxicity.",
     "action": "Halve the colchicine dose or avoid the combination; review blood counts.",
     "source": ["label"]},
    {"a": "ranolazine", "b": "nd_ccb", "severity": "major",
     "note": "Diltiazem/verapamil inhibit CYP3A4 and raise ranolazine levels, adding QT prolongation to their own rate-slowing effect.",
     "action": "Avoid the combination; if ranolazine is needed, choose a rate-control agent that is not a CYP3A4 inhibitor.",
     "source": ["label"]},
    {"a": "ranolazine", "b": "statin", "severity": "major",
     "note": "Ranolazine raises simvastatin exposure and the risk of myopathy.",
     "action": "Cap simvastatin at 20 mg or use a statin without this interaction, and warn about muscle pain.",
     "source": ["label"]},
    {"a": "ranolazine", "b": "amiodarone", "severity": "major",
     "note": "Both prolong the QT interval — the combination adds torsades risk.",
     "action": "Review the ECG/QTc before combining them and avoid other QT-prolonging drugs.",
     "source": ["label"]},
    {"a": "dronedarone", "b": "amiodarone", "severity": "major",
     "note": "Two antiarrhythmics with QT and bradycardic effects — no outcome benefit and real proarrhythmia risk.",
     "action": "Use one rhythm-control agent; specialist input before any switch.",
     "source": ["label", "af-2023"]},
    {"a": "dronedarone", "b": "digoxin", "severity": "major",
     "note": "Dronedarone inhibits P-gp and raises digoxin levels.",
     "action": "Halve the digoxin dose and check the level.",
     "source": ["label"]},
    {"a": "dronedarone", "b": "statin", "severity": "major",
     "note": "Dronedarone raises simvastatin exposure — myopathy risk.",
     "action": "Cap simvastatin at 10 mg or switch to a statin without this interaction.",
     "source": ["label"]},
    {"a": "dronedarone", "b": "anticoagulant", "severity": "moderate",
     "note": "Dronedarone inhibits P-gp and raises DOAC exposure; warfarin needs closer INR checks.",
     "action": "Review the anticoagulant dose and bleeding risk at each visit.",
     "source": ["label", "af-2023"]},
    {"a": "dronedarone", "b": "beta_blocker", "severity": "moderate",
     "note": "Both slow conduction — bradycardia and heart block are additive.",
     "action": "Check rate and ECG before and after starting either agent.",
     "source": ["label", "af-2023"]},
    {"a": "dronedarone", "b": "nd_ccb", "severity": "major",
     "note": "Diltiazem/verapamil inhibit CYP3A4 and raise dronedarone exposure, adding bradycardia and QT risk.",
     "action": "Avoid the combination; if rate control is needed, review the whole antiarrhythmic plan.",
     "source": ["label"]},
    {"a": "flecainide", "b": "amiodarone", "severity": "major",
     "note": "Two antiarrhythmics together — flecainide levels rise and ventricular proarrhythmia risk increases.",
     "action": "Specialist input only; monitor QRS and QTc closely if both are used.",
     "source": ["label", "af-2023"]},
    {"a": "flecainide", "b": "nd_ccb", "severity": "major",
     "note": "Both depress conduction and contractility — bradycardia, block and negative inotropy are additive.",
     "action": "Avoid combining them unless a specialist is supervising.",
     "source": ["label"]},
    {"a": "flecainide", "b": "beta_blocker", "severity": "moderate",
     "note": "Flecainide is usually paired with a rate-control agent, but both slow conduction.",
     "action": "Review the ECG for QRS widening and bradycardia after titration.",
     "source": ["label", "af-2023"]},
    {"a": "ticagrelor", "b": "statin", "severity": "moderate",
     "note": "Ticagrelor inhibits CYP3A4 and raises simvastatin exposure — myopathy risk.",
     "action": "Cap simvastatin at 40 mg or use a statin without this interaction.",
     "source": ["label"]},
    {"a": "ticagrelor", "b": "digoxin", "severity": "moderate",
     "note": "Ticagrelor inhibits P-gp and raises digoxin levels.",
     "action": "Check the digoxin level and monitor for toxicity when starting or stopping.",
     "source": ["label"]},
    {"a": "thiazide", "b": "loop_diuretic", "severity": "moderate",
     "note": "Two diuretics together deplete sodium and potassium faster than either alone.",
     "action": "Reserve the combination for resistant oedema, with electrolytes checked within a week.",
     "source": ["label", "hf-2022"]},
    {"a": "thiazide", "b": "digoxin", "severity": "moderate",
     "note": "Thiazide-induced hypokalaemia and hyponatraemia potentiate digoxin toxicity.",
     "action": "Monitor potassium, sodium and the digoxin level; replace electrolytes as needed.",
     "source": ["label", "af-2023"]},
    {"a": "thiazide", "b": "nsaid", "severity": "moderate",
     "note": "NSAIDs blunt the diuretic effect and, with a RAAS blocker, worsen renal function.",
     "action": "Avoid where possible; check creatinine and electrolytes within a week if used.",
     "source": ["label", "ckd-2024"]},
    {"a": "icosapent_ethyl", "b": "anticoagulant", "severity": "moderate",
     "note": "High-dose EPA adds to anticoagulant bleeding risk.",
     "action": "Monitor for bleeding after starting; review the anticoagulant indication.",
     "source": ["label", "ccd-2023"]},
    {"a": "fenofibrate", "b": "statin", "severity": "major",
     "note": "A fibrate with a statin raises the risk of myopathy and rhabdomyolysis.",
     "action": "Use the lowest effective doses, warn about muscle pain, and check CK if symptoms appear.",
     "source": ["label", "cholesterol-2018"]},
    {"a": "fenofibrate", "b": "anticoagulant", "severity": "major",
     "note": "Fenofibrate potentiates warfarin and raises INR.",
     "action": "Check INR more often after starting or changing the dose.",
     "source": ["label"]},
    {"a": "bempedoic_acid", "b": "statin", "severity": "moderate",
     "note": "Bempedoic acid on top of a statin adds to the myopathy risk, though less than a fibrate does.",
     "action": "Review muscle symptoms and CK if they appear; the combination is used when LDL remains above goal.",
     "source": ["label"]},
    {"a": "finerenone", "b": "ace_inhibitor", "severity": "major",
     "note": "Finerenone on a RAAS blocker is the intended combination, but potassium and creatinine must be checked — hyperkalaemia is the limiting adverse effect.",
     "action": "Check potassium and eGFR at 4 weeks and after any dose change; stop if K+ >5.5 mmol/L.",
     "source": ["ckd-2024"]},
    {"a": "finerenone", "b": "arb", "severity": "major",
     "note": "Finerenone on an ARB adds to hyperkalaemia risk in the same way it does on an ACE inhibitor.",
     "action": "Check potassium and eGFR at 4 weeks; hold finerenone during acute illness.",
     "source": ["ckd-2024"]},
    {"a": "finerenone", "b": "mra", "severity": "major",
     "note": "Two mineralocorticoid receptor antagonists do not add benefit and multiply the hyperkalaemia risk.",
     "action": "Use one MRA only; switch rather than stacking.",
     "source": ["ckd-2024", "hf-2022"]},
    {"a": "hydralazine_isosorbide", "b": "pde5_inhibitor", "severity": "major",
     "note": "A nitrate-containing vasodilator with a PDE5 inhibitor causes profound, refractory hypotension.",
     "action": "Contraindicated — separate by at least 24 h (48 h for tadalafil) and counsel the patient.",
     "source": ["label", "hf-2022"]},
    {"a": "nd_ccb", "b": "statin", "severity": "moderate",
     "note": "Diltiazem/verapamil inhibit CYP3A4 and raise simvastatin exposure — myopathy risk.",
     "action": "Cap simvastatin at 10 mg or use a statin without this interaction.",
     "source": ["label"]},
    {"a": "nd_ccb", "b": "digoxin", "severity": "moderate",
     "note": "Verapamil raises digoxin levels and both slow AV conduction.",
     "action": "Reduce the digoxin dose and monitor the level and heart rate.",
     "source": ["label", "af-2023"]},
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
        if tag == "statin_intolerance":
            add("statin_intolerance", "documented statin intolerance")
        if tag == "familial_hypercholesterolemia":
            add("familial_hypercholesterolemia", "familial hypercholesterolaemia in the history")
        if tag == "pancreatitis":
            add("pancreatitis", "previous pancreatitis")
        if tag == "angioedema":
            add("angioedema", "history of angioedema")
        if tag == "pregnancy":
            add("pregnancy", "pregnancy in the history")
        if tag == "refractory_angina":
            add("refractory_angina", "angina that persists despite standard therapy")

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
    # Named as its own reason: "dyslipidemia (LDL 165)" would be a false
    # attribution when non-HDL is the only fraction above its threshold.
    if derived.get("non_hdl_high") is not None:
        add("non_hdl_high", f"non-HDL {derived['non_hdl_high']:g} mg/dL")
    if derived.get("ldl_very_high") is not None:
        add("ldl_very_high", f"LDL {derived['ldl_very_high']:g} mg/dL (severe hypercholesterolaemia)")
    if derived.get("triglycerides_elevated") is not None:
        add("triglycerides_elevated", f"triglycerides {derived['triglycerides_elevated']:g} mg/dL")
    if derived.get("triglycerides_severe") is not None:
        add("triglycerides_severe", f"triglycerides {derived['triglycerides_severe']:g} mg/dL (pancreatitis risk)")
    if derived.get("albuminuria") is not None:
        add("albuminuria", f"UACR {derived['albuminuria']:g} mg/g")
    # Indications are OR-ed, so a drug that needs two facts together gets a
    # compound name here rather than a list of tags that would offer it on
    # either one. These four are the cases where a single fact is not the
    # indication.
    if "diabetes" in tags and derived.get("albuminuria") is not None:
        add("diabetic_kidney_disease", f"diabetes with albuminuria (UACR {derived['albuminuria']:g} mg/g)")
    if "diabetes" in tags and ({"established_cad", "prior_mi", "prior_pci_cabg"} & set(tags)):
        add("diabetes_with_ascvd", "diabetes with established atherosclerotic disease")
    if "pregnancy" in tags and "hypertension" in tags:
        add("pregnancy_hypertension", "hypertension in pregnancy")
    if derived.get("triglycerides_elevated") is not None and (
        {"established_cad", "prior_mi", "prior_pci_cabg", "diabetes"} & set(tags)
    ):
        add(
            "residual_hypertriglyceridaemia",
            f"triglycerides {derived['triglycerides_elevated']:g} mg/dL with ASCVD or diabetes",
        )
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
    risk_scores: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Recommend, flag and block medication options from the captured facts.

    ``risk_scores`` is the deterministic block from
    :mod:`backend.risk_score_context` (HEART, GRACE, CHA₂DS₂-VASc). The encounter
    urgency comes from it when it is complete, and CHA₂DS₂-VASc grades the
    stroke-risk reason behind the anticoagulation option; when it is absent or
    incomplete the review behaves exactly as it did before.
    """
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

    # CHA₂DS₂-VASc is a stroke-risk instrument, so it speaks only for a patient
    # in atrial fibrillation — and it grades the reason behind the
    # anticoagulation option rather than ordering it.
    stroke_risk = _score_band(risk_scores, "cha2ds2_vasc")
    stroke_risk_incomplete = False
    if "atrial_fibrillation" in tags and stroke_risk:
        if stroke_risk.get("score") is None:
            stroke_risk_incomplete = True
        else:
            indications["atrial_fibrillation_stroke_risk"] = (
                f"CHA2DS2-VASc {stroke_risk['score']}"
                f" ({stroke_risk.get('annual_stroke_risk_pct')}%/year)"
                f" — anticoagulation tier: {stroke_risk.get('anticoagulation_tier')}"
            )

    # The pooled cohort equation is a *chronic* risk, so it never escalates the
    # encounter the way HEART or GRACE do — it grades the reason behind the
    # lipid-lowering option, exactly as CHA₂DS₂-VASc grades the anticoagulation
    # reason. A ten-year probability is not an emergency.
    ascvd = _score_band(risk_scores, "ascvd")
    ascvd_reading: str | None = None
    ascvd_incomplete = False
    if ascvd:
        if ascvd.get("risk_pct") is None:
            ascvd_incomplete = True
        else:
            ascvd_reading = (
                f"ASCVD 10-year risk {ascvd['risk_pct']}% ({ascvd.get('category')}, "
                f"{ascvd.get('group')} equation)"
            )
            if ascvd.get("statin_indicated"):
                indications["ascvd_intermediate_risk"] = ascvd_reading

    recommendations: list[dict[str, Any]] = []
    contraindicated: list[dict[str, Any]] = []
    allergy_alerts: list[dict[str, Any]] = []

    for drug in sorted(DRUGS, key=lambda d: (d["priority"], d["name"])):
        key = drug["key"]
        triggered = {name: indications[name] for name in drug["indications"] if name in indications}
        # Key, not class: a patient on amiodarone is not "already documented" on
        # dronedarone, and one on metoprolol is not on labetalol. Class matching
        # here turned a different agent in the same class into a duplicate of a
        # prescription the patient does not have.
        already_on = key in current_keys
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

    # ARNI outranks the other RAAS strategies in HFrEF, so when it is offered an
    # ACE inhibitor or ARB is the alternative rather than a parallel option — and
    # an ACE inhibitor needs a 36-hour washout before the first ARNI dose.
    if "arni" in offered_keys:
        for rec in recommendations:
            if rec["drug_class"] in {"ace_inhibitor", "arb"} and rec["status"] == "recommended":
                rec["status"] = "alternative"
                rec["action"] = (
                    "Offer only if the ARNI is not tolerated, and observe the 36-hour washout "
                    "after an ACE inhibitor; never combine the two."
                )
                rec["review_flags"].append(
                    "ARNI is preferred in symptomatic HFrEF — one RAAS strategy at a time."
                )

    # Below the conventional threshold the option is still listed (the rhythm
    # and other indications decide), but the score says why it is not automatic.
    if (
        "atrial_fibrillation" in tags
        and stroke_risk.get("anticoagulation_tier") == "none"
        and "atrial_fibrillation_stroke_risk" in indications
    ):
        note = (
            f"CHA2DS2-VASc {stroke_risk['score']} — below the conventional anticoagulation "
            "threshold, so this is a rhythm/indication decision rather than an automatic one."
        )
        for rec in recommendations:
            if _CLASS_OF.get(_KEY_BY_NAME.get(rec["drug"], ""), "") == "anticoagulant" and note not in rec["review_flags"]:
                rec["review_flags"].append(note)

    # Below the threshold the equation still speaks: it says why a statin is not
    # automatic instead of leaving the guideline out of the note.
    if ascvd_reading and not ascvd.get("statin_indicated"):
        note = (
            f"{ascvd_reading} — below the 7.5% threshold for an automatic statin, so the "
            "decision turns on the rest of the risk profile and the clinician-patient discussion."
        )
        for rec in recommendations:
            if rec["drug_class"] == "statin" and note not in rec["review_flags"]:
                rec["review_flags"].append(note)

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
    if stroke_risk_incomplete:
        missing.append(
            "CHA2DS2-VASc incomplete ("
            + ", ".join(stroke_risk.get("missing") or [])
            + ") — stroke risk is not graded for this atrial fibrillation."
        )
    # Only worth saying when a laboratory panel did come in: an encounter with no
    # labs at all already reports that the renal gates were not applied.
    if ascvd_incomplete and labs:
        missing.append(
            "ASCVD 10-year risk incomplete ("
            + ", ".join(ascvd.get("missing") or [])
            + ") — the primary-prevention statin decision is not graded."
        )

    pathway = _pathway(risk_level, indications, derived, risk_scores)

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
        "risk_scores": risk_scores or None,
        "summary": summary,
        "disclaimer": DISCLAIMER,
    }


def _score_band(risk_scores: dict[str, Any] | None, name: str) -> dict[str, Any]:
    """One score's summary from the assembled block, or an empty dict."""
    if not isinstance(risk_scores, dict):
        return {}
    score = risk_scores.get(name)
    return score if isinstance(score, dict) else {}


def _pathway(
    risk_level: str | None,
    indications: dict[str, str],
    derived: dict[str, float],
    risk_scores: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Urgency of the *encounter*, so medication choices never delay escalation.

    The deterministic scores decide first, because they are checkable: a raised
    troponin, then HEART or GRACE in their high band, then the model's screening
    band, then a chest-pain presentation. The older triggers stay as the
    fallback for encounters the scores cannot grade (missing vitals, no
    chest-pain history), so nothing escalates less than it did before — and
    ``drivers`` names whichever instrument decided, so the clinician can see
    *why* the encounter is being called an emergency.
    """
    heart = _score_band(risk_scores, "heart")
    grace = _score_band(risk_scores, "grace")

    def reading(name: str, score: dict[str, Any]) -> str:
        total, band = score["score"], score["band"]
        if name == "HEART":
            return f"HEART {total} ({band}, 6-week MACE {score.get('mace_risk_6_weeks')})"
        bound = {"low": "<109", "intermediate": "109-140", "high": ">140"}.get(band, "")
        mortality = (score.get("in_hospital_mortality") or {}).get("percent")
        tail = f" — in-hospital mortality {mortality:g}%" if mortality else ""
        return f"GRACE {total} ({bound}, {band}){tail}"

    complete = [
        (name, score)
        for name, score in (("HEART", heart), ("GRACE", grace))
        if score.get("score") is not None
    ]
    drivers = [reading(name, score) for name, score in complete if score.get("band") == "high"]
    intermediate = [reading(name, score) for name, score in complete if score.get("band") == "intermediate"]

    if derived.get("troponin_elevated") is not None:
        return {
            "urgency": "emergency",
            "statement": "Treat as possible acute coronary syndrome: stabilise and escalate on clinical grounds.",
            "rationale": [
                "Troponin is above the reference limit",
                "Do not delay emergency assessment, ECG or biomarkers for outpatient medication titration.",
            ] + drivers,
            "drivers": ["troponin"] + drivers,
        }
    if drivers:
        return {
            "urgency": "emergency",
            "statement": "Treat as possible acute coronary syndrome: stabilise and escalate on clinical grounds.",
            "rationale": drivers + [
                "Deterministic score in its high band — do not delay emergency assessment, ECG or biomarkers.",
            ],
            "drivers": drivers,
        }
    if risk_level == "High":
        return {
            "urgency": "emergency",
            "statement": "Treat as possible acute coronary syndrome: stabilise and escalate on clinical grounds.",
            "rationale": [
                "Screening band is High",
                "Do not delay emergency assessment, ECG or biomarkers for outpatient medication titration.",
            ],
            "drivers": ["screening band"],
        }
    if "suspected_acs" in indications:
        # The presentation is a floor, not a contest: a score in a lower band
        # refines the reading but never softens the ACS pathway (ADR-018). Its
        # numbers are still shown, so the reason the urgency exceeds the score
        # is explicit rather than unexplained.
        graded = [reading(name, score) for name, score in complete]
        return {
            "urgency": "emergency",
            "statement": "Chest pain reported: treat as possible acute coronary syndrome until excluded.",
            "rationale": [
                "Chest pain is the trigger for the ACS pathway regardless of the medication options.",
            ] + [f"Graded as {line} — the pathway is not softened by a lower band." for line in graded],
            "drivers": ["presentation"] + graded,
        }

    if intermediate or risk_level == "Medium":
        return {
            "urgency": "urgent",
            "statement": "Arrange same-day or next-day clinical review; medication changes are for that review.",
            "rationale": (intermediate + (["Screening band is Medium."] if risk_level == "Medium" else [])),
            "drivers": intermediate or ["screening band"],
        }
    return {
        "urgency": "routine",
        "statement": "Routine review: options below are for planned, clinician-led prescribing.",
        "rationale": ["No emergency trigger captured in this encounter."],
        "drivers": [],
    }
