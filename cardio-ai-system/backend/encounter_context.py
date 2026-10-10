"""Assemble the patient context a medication safety review is judged against.

Why this exists
---------------
Two callers ask the same question of the same rules: the workspace page
(``POST /medication-review``) and the live copilot loop, which rebuilds the
screen with every spoken line. If each assembled the context itself, the page
and the consultation could disagree about the same patient — the worst possible
outcome for a safety screen. So the union rules live here, once:

- **conditions/history** — the visit details the clinician recorded, the risk
  factors the entity extractor finds, and the wider condition vocabulary run
  over the wording itself (a condition said out loud counts even when no form
  field mentions it).
- **allergies** — the recorded list plus explicit "allergic to …" phrases.
- **current medications** — names and brands from the record plus the ones the
  encounter names, de-duplicated case-insensitively.
- **labs** — numeric findings parsed from the report text (unit-aware, via
  :func:`backend.lab_report.labs_for_review`), with caller-supplied values
  overriding the parsed ones.
- **symptoms** — what the vocabulary extracts from the whole narrative, unioned
  with the caller's (already learned-vocabulary-aware) findings for the current
  line, so nothing found mid-visit is lost.

Nothing is stored; the same text always produces the same context.
"""

from __future__ import annotations

from typing import Any

from agents.nlp_symptom_agent import extract_symptoms_from_text
from agents.pharmacology_agent import as_list, detect_conditions, extract_allergy_mentions
from backend.lab_report import labs_for_review
from backend.medical_entities import extract_entities


def build_medication_context(
    encounter_text: str = "",
    report_text: str = "",
    patient: dict | None = None,
    symptoms: list[str] | None = None,
) -> dict[str, Any]:
    """Union what the record says with what the encounter text states."""
    context = patient if isinstance(patient, dict) else {}
    narrative = f"{encounter_text or ''}\n{report_text or ''}".strip()
    entities = extract_entities(narrative) if narrative else {
        "medications": [], "durations": [], "risk_factors": []
    }
    allergies_from_text = extract_allergy_mentions(narrative)

    conditions = as_list(context.get("conditions"))
    stated = list(entities.get("risk_factors") or []) + detect_conditions(narrative)
    for candidate in stated:
        tag = str(candidate).strip()
        if tag and tag not in conditions:
            conditions.append(tag)

    allergies = as_list(context.get("allergies"))
    for term in allergies_from_text:
        if term not in allergies:
            allergies.append(term)

    current = as_list(context.get("current_medications"))
    documented = {name.lower() for name in current}
    for medication in entities.get("medications") or []:
        name = str(medication.get("name", "")).strip()
        if name and name.lower() not in documented:
            current.append(name)
            documented.add(name.lower())

    try:
        age = int(str(context.get("age")).strip()) if str(context.get("age") or "").strip() else None
    except (TypeError, ValueError):
        age = None

    detected = extract_symptoms_from_text(narrative) if narrative else []
    for symptom in symptoms or []:
        if symptom not in detected:
            detected.append(symptom)

    pregnancy = context.get("pregnancy")

    return {
        "narrative": narrative,
        "entities": entities,
        "allergies_from_text": allergies_from_text,
        "conditions": conditions,
        "allergies": allergies,
        "current_medications": current,
        "age": age,
        "sex": context.get("sex") or None,
        "labs": labs_for_review(
            report_text,
            context.get("labs") if isinstance(context.get("labs"), dict) else None,
        ),
        "symptoms": detected,
        # None (not False) means "not recorded", which the review reports as a
        # gap rather than silently treating the patient as not pregnant.
        "pregnancy": pregnancy if isinstance(pregnancy, bool) else None,
    }
