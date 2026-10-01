"""Suggestion attribution: the guideline or reason behind every suggestion.

Why this exists
---------------
The hallucination review asked for "a source or reason beside every
suggested question" and "show which guideline backs each suggestion".
PulseIQ's copilot plans are generated either by the deterministic rule
engine or by the local LLM — neither currently says WHY a line is on the
list, so the doctor cannot tell a well-grounded suggestion from a fluent
guess.

Design
------
This is a deterministic keyword-to-source map, not an LLM call: the source
must be stable and verifiable, so it is rule-derived from the text of the
suggestion itself. Every suggestion gets a source — the fallback states
plainly that it came from this encounter's history rather than pretending
a guideline said it.

Sources cited: ACC/AHA chest pain guideline (2021), ESC ACS guideline
(2023/2024), ACEP chest pain policy, AHA/ACC heart failure and prevention
guidelines, HRS ambulatory rhythm guidance, standard OPQRST history.
"""

from __future__ import annotations

from typing import Iterable

# (keyword, source) — first match wins; keywords checked in order so the
# most specific guideline attribution beats the generic fallbacks.
_QUESTION_SOURCES: list[tuple[str, str]] = [
    ("jaw", "ACC/AHA chest pain guideline — cardiac radiation pattern"),
    ("arm", "ACC/AHA chest pain guideline — cardiac radiation pattern"),
    ("radiat", "ACC/AHA chest pain guideline — cardiac radiation pattern"),
    ("how long", "OPQRST history — Timing (standard chest-pain history)"),
    ("how long does each episode", "OPQRST history — Timing"),
    ("when the symptoms started", "OPQRST history — Onset"),
    ("started", "OPQRST history — Onset"),
    ("trigger or relieve", "OPQRST history — Provocation/Relief (angina assessment)"),
    ("exertion", "ACC/AHA chest pain guideline — exertional angina assessment"),
    ("worsen with exertion", "ACC/AHA chest pain guideline — exertional angina assessment"),
    ("sweating", "ACEP chest pain policy — autonomic associated symptoms"),
    ("nausea", "ACEP chest pain policy — autonomic associated symptoms"),
    ("breathless", "ACC/AHA dyspnea workup — dyspnea at rest vs exertion"),
    ("lying flat", "AHA/ACC heart failure guideline — orthopnea assessment"),
    ("blood pressure", "ACC/AHA primary prevention — modifiable risk factors"),
    ("diabetes", "ACC/AHA primary prevention — modifiable risk factors"),
    ("smoking", "ACC/AHA primary prevention — modifiable risk factors"),
    ("family history", "ACC/AHA — family history of premature ASCVD"),
    ("severe", "ACEP chest pain policy — severity grading"),
    ("0 to 10", "OPQRST history — Severity grading"),
    ("scale", "OPQRST history — Severity grading"),
    ("irregular", "ACC/AHRQ palpitations workup — rhythm documentation"),
    ("skipped beats", "ACC/AHRQ palpitations workup — rhythm documentation"),
    ("fainting", "ESC syncope guideline — red-flag syncope assessment"),
    ("loss of consciousness", "ESC syncope guideline — red-flag syncope assessment"),
    ("pitting", "AHA/ACC heart failure guideline — peripheral oedema assessment"),
    ("dry or productive", "Differential for nocturnal cough — HF vs pulmonary"),
    ("vomiting", "ACEP chest pain policy — associated symptoms"),
    ("severity", "OPQRST history — Severity grading"),
    ("relieved", "OPQRST history — Relief (nitrate response)"),
    ("what is the main problem", "Opening history — patient's own words first"),
]

_TEST_SOURCES: list[tuple[str, str]] = [
    ("ecg", "ESC ACS guideline — ECG within 10 minutes of first medical contact"),
    ("troponin", "ESC 0/1h–0/2h troponin algorithm / ACC-AHA serial biomarkers"),
    ("biomarker", "ACC/AHA — serial cardiac biomarkers"),
    ("bnp", "AHA/ACC heart failure guideline — natriuretic peptides in dyspnea"),
    ("nt-probnp", "AHA/ACC heart failure guideline — natriuretic peptides"),
    ("x-ray", "AHA/ACC — chest radiograph in acute dyspnea"),
    ("holter", "ACC/AHA/HRS ambulatory ECG monitoring guideline"),
    ("rhythm strip", "ACC/AHA/HRS ambulatory ECG monitoring guideline"),
    ("echo", "AHA/ACC — echocardiography for structural heart disease"),
    ("pulse ox", "ACEP chest pain policy — initial vital signs"),
    ("vital", "ACEP chest pain policy — initial vital signs"),
    ("monitoring", "ACEP chest pain policy — observation in suspected ACS"),
    ("lipid", "ACC/AHA — lipid panel for cardiovascular risk assessment"),
    ("hba1c", "ADA/ACC — glycaemic assessment in cardiovascular risk"),
    ("glucose", "ADA/ACC — glycaemic assessment in cardiovascular risk"),
    ("cbc", "Standard admission bloods — anaemia/infection screen"),
    ("renal", "ACC/AHA — renal function before contrast or ACE-inhibitor therapy"),
]

_STEP_SOURCES: list[tuple[str, str]] = [
    ("correlate", "Standard of care — integrate symptoms, ECG and biomarkers"),
    ("escalate", "ESC/ACC AHA — red-flag escalation criteria"),
    ("emergency", "ESC — immediate emergency pathway for red flags"),
    ("document", "Medical-legal standard — contemporaneous documentation"),
    ("risk factor", "ACC/AHA 2018 prevention guideline — risk factor modification"),
    ("follow", "Standard follow-up practice after cardiac assessment"),
    ("monitor", "ACEP chest pain policy — reassessment intervals"),
    ("reassess", "ACEP chest pain policy — reassessment intervals"),
]

_FALLBACK_QUESTION = "History-taking standard — derived from this encounter (no single guideline)"
_FALLBACK_TEST = "Standard workup for the detected symptom pattern"
_FALLBACK_STEP = "Clinical judgment — applies to this encounter's findings"


def _match(item: str, table: list[tuple[str, str]], fallback: str) -> str:
    lowered = item.lower()
    for keyword, source in table:
        if keyword in lowered:
            return source
    return fallback


def attribute_suggestions(
    doctor_questions: Iterable[str],
    recommended_tests: Iterable[str],
    next_steps: Iterable[str],
) -> dict[str, str]:
    """Map every suggestion to the guideline/reason that backs it.

    Returns a flat ``{suggestion text: source}`` dict covering all three
    lists. Keys are the exact suggestion strings the UI renders, so the
    frontend can look them up directly.
    """
    sources: dict[str, str] = {}
    for question in doctor_questions:
        if question:
            sources[question] = _match(question, _QUESTION_SOURCES, _FALLBACK_QUESTION)
    for test in recommended_tests:
        if test:
            sources[test] = _match(test, _TEST_SOURCES, _FALLBACK_TEST)
    for step in next_steps:
        if step:
            sources[step] = _match(step, _STEP_SOURCES, _FALLBACK_STEP)
    return sources


def plan_confidence(symptoms: list[str], report_text: str, probability: float) -> dict[str, str]:
    """Plan-level confidence the assistant can show — and admit ignorance.

    Three honest tiers:
    - ``low`` + ``insufficient_information`` when nothing has been detected
      yet — the assistant says "not enough information" instead of guessing.
    - ``moderate`` for a single-sided probability (borderline 0.5) or few
      detected concepts.
    - ``high`` only with multiple corroborating concepts and a decisive
      probability.
    """
    n = len(symptoms)
    decisive = abs(float(probability) - 0.5) >= 0.3
    if n == 0 and not (report_text or "").strip():
        return {
            "confidence": "low",
            "insufficient_information": "true",
            "reason": "No concepts or report context yet — ask an open question before drawing conclusions.",
        }
    if n == 0 or not decisive:
        return {
            "confidence": "low",
            "insufficient_information": "false",
            "reason": f"Only {n} concept(s) detected and/or a borderline probability — treat every suggestion as provisional.",
        }
    if n >= 3 and decisive:
        return {
            "confidence": "high",
            "insufficient_information": "false",
            "reason": f"{n} corroborating concepts with a decisive probability ({probability:.0%}).",
        }
    return {
        "confidence": "moderate",
        "insufficient_information": "false",
        "reason": f"{n} concept(s) with probability {probability:.0%} — confirm with exam and testing.",
    }
