"""Medical entity extraction: medications, durations, risk factors.

Why this exists
---------------
The speech/NLP review asked for "medical entity extraction (symptoms,
medications, durations, risk factors) and a structured summary or SOAP
note". PulseIQ already extracts the nine clinical *symptom* concepts
(``nlp_symptom_agent``); this module covers the other three entity
classes the review named, in the same deterministic, rule-first style:
regex over the transcript, English + Urdu/Roman-Urdu where it matters,
negation-aware (``no diabetes`` must not count as diabetes).

Output feeds the SOAP note builder (``soap_note``) so the structured
summary is derived from entities actually present in the transcript —
never invented.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Medications — common cardiac/cardiovascular drugs with dose patterns
# ---------------------------------------------------------------------------

_MEDICATIONS: list[tuple[str, re.Pattern[str]]] = [
    ("aspirin", re.compile(r"\b(?:aspirin|disprin|ecosprin|aspin)\b(?:\s+(\d+)\s*mg)?", re.I)),
    ("clopidogrel", re.compile(r"\b(?:clopidogrel|plavix)\b(?:\s+(\d+)\s*mg)?", re.I)),
    ("atorvastatin", re.compile(r"\b(?:atorvastatin|lipitor)\b(?:\s+(\d+)\s*mg)?", re.I)),
    ("rosuvastatin", re.compile(r"\b(?:rosuvastatin|crestor)\b(?:\s+(\d+)\s*mg)?", re.I)),
    ("metoprolol", re.compile(r"\b(?:metoprolol|lopressor|betaloc)\b(?:\s+(\d+)\s*mg)?", re.I)),
    ("bisoprolol", re.compile(r"\bbisoprolol\b(?:\s+(\d+)\s*mg)?", re.I)),
    ("carvedilol", re.compile(r"\bcarvedilol\b(?:\s+(\d+)\s*mg)?", re.I)),
    ("ramipril", re.compile(r"\bramipril\b(?:\s+(\d+)\s*mg)?", re.I)),
    ("enalapril", re.compile(r"\benalapril\b(?:\s+(\d+)\s*mg)?", re.I)),
    ("lisinopril", re.compile(r"\blisinopril\b(?:\s+(\d+)\s*mg)?", re.I)),
    ("losartan", re.compile(r"\blosartan\b(?:\s+(\d+)\s*mg)?", re.I)),
    ("amlodipine", re.compile(r"\bamlodipine\b(?:\s+(\d+)\s*mg)?", re.I)),
    ("nifedipine", re.compile(r"\bnifedipine\b(?:\s+(\d+)\s*mg)?", re.I)),
    ("furosemide", re.compile(r"\b(?:furosemide|lasix)\b(?:\s+(\d+)\s*mg)?", re.I)),
    ("spironolactone", re.compile(r"\bspironolactone\b(?:\s+(\d+)\s*mg)?", re.I)),
    ("digoxin", re.compile(r"\bdigoxin\b(?:\s+(\d+(?:\.\d+)?)\s*mcg)?", re.I)),
    ("amiodarone", re.compile(r"\bamiodarone\b(?:\s+(\d+)\s*mg)?", re.I)),
    ("nitroglycerin", re.compile(r"\b(?:nitroglycerin|glyceryl\s+trinitrate|gtn|nitro)\b(?:\s+(?:spray|tablet))?", re.I)),
    ("warfarin", re.compile(r"\bwarfarin\b(?:\s+(\d+)\s*mg)?", re.I)),
    ("apixaban", re.compile(r"\bapixaban\b(?:\s+(\d+)\s*mg)?", re.I)),
    ("rivaroxaban", re.compile(r"\brivaroxaban\b(?:\s+(\d+)\s*mg)?", re.I)),
    ("metformin", re.compile(r"\bmetformin\b(?:\s+(\d+)\s*mg)?", re.I)),
    ("glyceryl", re.compile(r"\bglyceryl\b", re.I)),  # placeholder-free dup guard
]

# Symptom-word medications must not swallow: "aspirin" is a drug; there is
# no ambiguity worth extra handling.

_NEGATION_BEFORE = re.compile(
    r"\b(?:no|not|denies|denied|without|stopped|discontinued|allergic to|allergy to)\s+(?:\w+\s+){0,2}$",
    re.I,
)

# ---------------------------------------------------------------------------
# Durations — "for 3 days", "since monday", "2 hours", "for a month"
# ---------------------------------------------------------------------------

_DURATION = re.compile(
    r"\b(?:for\s+)?(\d+(?:\.\d+)?)\s*"
    r"(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?|months?|years?)\b"
    r"|(?:for\s+)(a|an|one|two|three|four|five|ten|fifteen|thirty)\s+"
    r"(minute|hour|day|week|month|year)s?\b"
    r"|\bsince\s+(yesterday|today|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"last\s+(?:night|week|month|year)|morning|this\s+morning|childhood|teenage)",
    re.I,
)

_DURATION_UNIT_KEY = {
    "second": "seconds", "sec": "seconds", "seconds": "seconds", "secs": "seconds",
    "minute": "minutes", "min": "minutes", "minutes": "minutes", "mins": "minutes",
    "hour": "hours", "hr": "hours", "hours": "hours", "hrs": "hours",
    "day": "days", "days": "days",
    "week": "weeks", "weeks": "weeks",
    "month": "months", "months": "months",
    "year": "years", "years": "years",
}
_WORD_NUMBERS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "ten": 10, "fifteen": 15, "thirty": 30,
}

# ---------------------------------------------------------------------------
# Risk factors — present only if not negated
# ---------------------------------------------------------------------------

_RISK_FACTORS: list[tuple[str, re.Pattern[str]]] = [
    ("diabetes", re.compile(r"\b(?:diabet(?:es|ic)|sugar\s+(?:problem|high)|type\s*[12]\s*diabet)", re.I)),
    ("hypertension", re.compile(r"\b(?:hypertension|high\s+(?:blood\s+pressure|bp)|bp\s+(?:high|raised))\b", re.I)),
    ("smoking", re.compile(r"\b(?:smok(?:e|es|ing|er)|cigarette|bidis?)\b", re.I)),
    ("family history of premature CAD", re.compile(
        r"\b(?:family\s+history|fhx|father(?:'s)?\s+(?:side\s+)?(?:had\s+)?" +
        r"(?:heart\s+attack|mi)|mother(?:'s)?\s+(?:had\s+)?heart\s+attack)\b", re.I)),
    ("dyslipidemia", re.compile(r"\b(?:high\s+cholesterol|hyperlipid(?:a)?emia|dyslipidemia)\b", re.I)),
    ("obesity", re.compile(r"\b(?:obes(?:e|ity)|overweight|bmi\s*(?:over|>)\s*\d+)\b", re.I)),
    ("prior myocardial infarction", re.compile(r"\b(?:previous|prior|old)\s+(?:heart\s+attack|myocardial\s+infarction|\bmi\b)\b|\bpost[- ]?mi\b", re.I)),
    ("prior PCI or CABG", re.compile(r"\b(?:pci|stent(?:ed)?|cabg|bypass\s+surgery|angioplasty)\b", re.I)),
    ("chronic kidney disease", re.compile(r"\b(?:ckd|chronic\s+kidney|renal\s+insufficiency)\b", re.I)),
    ("atrial fibrillation", re.compile(r"\b(?:atrial\s+fibrillation|\baf\b|afi\b|irregular\s+heartbeat\s+diagnosed)\b", re.I)),
]

_NEGATION_WINDOW = re.compile(
    r"(?:^|[,;.\s])(?:no|not|denies|denied|negative\s+for|without|never\s+(?:had|had\s+)|nil\s+(?:\w+\s+){0,2})\s+$",
    re.I,
)


def _negated(text: str, match_start: int) -> bool:
    """True when the 60 characters before the match express negation."""
    prefix = text[max(0, match_start - 60):match_start]
    return bool(_NEGATION_WINDOW.search(prefix.lower() + " ") or _NEGATION_BEFORE.search(prefix + " "))


def extract_medications(text: str) -> list[dict[str, Any]]:
    """Medications mentioned (and not negated), with dose when stated."""
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for name, pattern in _MEDICATIONS:
        if name == "glyceryl":  # covered by nitroglycerin alias
            continue
        for match in pattern.finditer(text):
            if name in seen or _negated(text, match.start()):
                continue
            seen.add(name)
            dose = match.group(1) if match.groups() and match.group(1) else None
            found.append({"name": name, "dose_mg": dose, "matched": match.group(0).strip()})
    return found


def extract_durations(text: str) -> list[str]:
    """Duration expressions for how long a symptom has been present."""
    out: list[str] = []
    for match in _DURATION.finditer(text):
        raw = " ".join(match.group(0).split()).strip()
        low = raw.lower()
        if low.startswith("for "):
            low = low[4:]
        if low not in out:
            out.append(low)
        if len(out) >= 8:
            break
    return out


def extract_risk_factors(text: str) -> list[str]:
    """Risk factors present in the text, skipping negated mentions."""
    found: list[str] = []
    for name, pattern in _RISK_FACTORS:
        match = pattern.search(text)
        if match and not _negated(text, match.start()):
            found.append(name)
    return found


def extract_entities(text: str) -> dict[str, Any]:
    """All three entity classes in one pass over the transcript."""
    clean = str(text or "")
    return {
        "medications": extract_medications(clean),
        "durations": extract_durations(clean),
        "risk_factors": extract_risk_factors(clean),
    }


# ---------------------------------------------------------------------------
# SOAP note — structured summary derived strictly from what is present
# ---------------------------------------------------------------------------

def build_soap_note(
    transcript: str,
    symptoms: list[str],
    report_text: str = "",
    risk_level: str = "Low",
) -> dict[str, Any]:
    """Build a structured SOAP note from the encounter.

    S/O come from what was actually captured (transcript entities, symptom
    concepts, report values); A is the risk band plus an explicit
    "pending" qualifier — the assistant suggests, the clinician diagnoses;
    P lists the captured next steps as options for the clinician to confirm.
    Nothing here is generated text — it is a structured restatement, so it
    cannot hallucinate content that is not in the encounter.
    """
    text = str(transcript or "")
    entities = extract_entities(text)
    report = str(report_text or "")

    subjective_bits: list[str] = []
    if symptoms:
        subjective_bits.append("Reported concepts: " + ", ".join(symptoms) + ".")
    if entities["durations"]:
        subjective_bits.append("Duration: " + "; ".join(entities["durations"]) + ".")
    if entities["medications"]:
        meds = ", ".join(
            m["name"] + (f" {m['dose_mg']} mg" if m["dose_mg"] else "")
            for m in entities["medications"]
        )
        subjective_bits.append("Current medications mentioned: " + meds + ".")
    if not subjective_bits:
        subjective_bits.append("No symptom or medication detail captured yet.")

    objective_bits: list[str] = []
    if entities["risk_factors"]:
        objective_bits.append("Risk factors: " + ", ".join(entities["risk_factors"]) + ".")
    if report.strip():
        objective_bits.append("Report context: " + " ".join(report.split())[:400])
    else:
        objective_bits.append("No report or examination findings entered.")

    return {
        "subjective": subjective_bits,
        "objective": objective_bits,
        "assessment": [
            f"Screening risk band: {risk_level} (screening estimate from captured text — not a diagnosis)."
        ],
        "plan": [
            "Confirm assessment with examination, ECG and biomarkers as indicated.",
            "Clinician to select and order tests; assistant suggests only.",
            "Reassess if red-flag symptoms appear.",
        ],
        "entities": entities,
        "note": "Structured from captured encounter content only — review before filing.",
    }
