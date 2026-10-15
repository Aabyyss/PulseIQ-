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
  encounter names.

The record comes first and wins on spelling: every list is merged
case-insensitively (a recorded "Aspirin" and a spoken "aspirin" are one
allergy, not two), and the spelling that is kept is the one the clinician
typed.
- **labs** — numeric findings parsed from the report text *and* from what was
  said out loud (unit-aware, via :func:`backend.lab_report.labs_for_review`):
  a clinician reading "eGFR 26" off the note is the same fact as pasting it,
  and the live screen must not ignore one of them. Three sources, most
  deliberate last — speech, then the written report text, then the recorded
  fields, so a value the clinician deliberately entered always wins.
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


class _Merge:
    """An order-preserving, case-insensitive set of clinical terms.

    The review's lists are read by a clinician and matched by rules, so a term
    that is recorded and then said out loud has to appear once, with the spelling
    the record used: "Aspirin" in the allergies field plus "allergic to aspirin"
    in the transcript is one allergy, and showing it twice reads as two.
    Whitespace is collapsed and case is folded for the comparison only.
    """

    def __init__(self, existing: list[str]) -> None:
        self._items: list[str] = []
        self._seen: set[str] = set()
        for item in existing:
            self.add(item)

    @staticmethod
    def _key(value: str) -> str:
        return " ".join(str(value or "").split()).casefold()

    def add(self, value: str) -> None:
        cleaned = " ".join(str(value or "").split())
        if not cleaned:
            return
        key = self._key(cleaned)
        if key in self._seen:
            return
        self._seen.add(key)
        self._items.append(cleaned)

    def __iter__(self):
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)


def _merge(values: list[str]) -> _Merge:
    return _Merge(values)


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

    conditions = _merge(as_list(context.get("conditions")))
    stated = list(entities.get("risk_factors") or []) + detect_conditions(narrative)
    for candidate in stated:
        conditions.add(candidate)

    allergies = _merge(as_list(context.get("allergies")))
    for term in allergies_from_text:
        allergies.add(term)

    current = _merge(as_list(context.get("current_medications")))
    for medication in entities.get("medications") or []:
        current.add(str(medication.get("name", "")))

    try:
        age = int(str(context.get("age")).strip()) if str(context.get("age") or "").strip() else None
    except (TypeError, ValueError):
        age = None

    detected = extract_symptoms_from_text(narrative) if narrative else []
    for symptom in symptoms or []:
        if symptom not in detected:
            detected.append(symptom)

    pregnancy = context.get("pregnancy")
    # Read aloud during the visit, then the report text the clinician typed or
    # pasted (which wins where both state a value), then the recorded fields.
    labs = labs_for_review(encounter_text)
    labs.update(labs_for_review(report_text))
    if isinstance(context.get("labs"), dict):
        labs.update(labs_for_review("", context["labs"]))

    return {
        "narrative": narrative,
        "entities": entities,
        "allergies_from_text": allergies_from_text,
        "conditions": list(conditions),
        "allergies": list(allergies),
        "current_medications": list(current),
        "age": age,
        "sex": context.get("sex") or None,
        "labs": labs,
        "symptoms": detected,
        # None (not False) means "not recorded", which the review reports as a
        # gap rather than silently treating the patient as not pregnant.
        "pregnancy": pregnancy if isinstance(pregnancy, bool) else None,
    }
