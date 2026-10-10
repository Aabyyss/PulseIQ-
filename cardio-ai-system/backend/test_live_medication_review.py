"""Live medication safety screen — the review the copilot recomputes per line.

Every case asserts a clinical direction on the *live* path: the visit details
the clinician recorded must count, an allergy said out loud must block with the
form left empty, a later line must add to the screen instead of replacing it,
and a cleared transcript must leave nothing stale behind. Runnable via pytest
and directly (``python backend/test_live_medication_review.py``).
"""

import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend import realtime_service  # noqa: E402
from backend.encounter_context import build_medication_context  # noqa: E402
from backend.realtime_service import (  # noqa: E402
    medication_review_for_encounter,
    process_live_transcript_entry,
)


def _rec(review: dict, needle: str) -> dict | None:
    for item in review["recommendations"]:
        if needle.lower() in item["drug"].lower():
            return item
    return None


def _blocked(review: dict, needle: str) -> dict | None:
    for item in review["contraindicated"]:
        if needle.lower() in item["drug"].lower():
            return item
    return None


def _allergy_alert(review: dict, needle: str) -> dict | None:
    for item in review["allergy_alerts"]:
        if needle.lower() in item["drug"].lower():
            return item
    return None


def _visit(**overrides) -> dict:
    """A typical visit header: a 68-year-old man, nothing unusual recorded."""
    base = {
        "age": "68",
        "sex": "Male",
        "conditions": ["hypertension"],
        "allergies": ["none"],
        "current_medications": ["none recorded"],
        "pregnancy": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Visit details count from the first line
# ---------------------------------------------------------------------------

def test_recorded_allergy_blocks_before_a_single_line_is_spoken():
    review = medication_review_for_encounter(
        "", "", patient=_visit(allergies=["aspirin"], conditions=["hypertension", "prior MI"])
    )
    alert = _allergy_alert(review, "aspirin")
    assert alert is not None
    assert "aspirin" in alert["matched_terms"]
    assert alert["alternative"]
    assert "prior_mi" in review["patient_profile"]["conditions"]


def test_recorded_conditions_are_mapped_to_tags():
    review = medication_review_for_encounter("", "", patient=_visit(conditions=["stent 2023", "asthma"]))
    tags = review["patient_profile"]["conditions"]
    assert "prior_pci_cabg" in tags
    assert "obstructive_airway_disease" in tags


def test_recorded_labs_override_what_the_report_text_says():
    review = medication_review_for_encounter(
        "diabetes",
        "eGFR 26",
        patient=_visit(conditions=["diabetes"], labs={"egfr": 58}),
    )
    assert review["patient_profile"]["labs_considered"]["renal_impairment"] == 58
    assert review["patient_profile"]["labs_considered"].get("renal_severe") is None


# ---------------------------------------------------------------------------
# What is said out loud counts even when the form is empty
# ---------------------------------------------------------------------------

def test_allergy_phrase_in_a_line_blocks_with_an_empty_allergy_field():
    review = medication_review_for_encounter(
        "he is allergic to aspirin and came in with chest pain",
        patient=_visit(allergies=[""], conditions=["hypertension"]),
    )
    alert = _allergy_alert(review, "aspirin")
    assert alert is not None
    assert "aspirin" in review["extracted"]["allergies_from_text"]
    assert _rec(review, "aspirin") is None


def test_condition_said_out_loud_is_tagged_even_though_no_field_mentions_it():
    review = medication_review_for_encounter(
        "crushing chest pain since an hour, and he also has asthma",
        patient=_visit(),
    )
    assert "obstructive_airway_disease" in review["patient_profile"]["conditions"]
    beta_blocker = _blocked(review, "beta-blocker")
    assert beta_blocker is not None
    assert beta_blocker["status"] == "review-before-use"
    assert "asthma" in " ".join(block["note"].lower() for block in beta_blocker["blocks"])


def test_medication_named_out_loud_is_screened_against_the_plan():
    review = medication_review_for_encounter(
        "patient reports crushing chest pain; he takes warfarin 5 mg daily",
        patient=_visit(current_medications=[]),
    )
    documented = review["patient_profile"]["current_medications"]
    assert len(documented) == 1  # named once, recorded nowhere else
    assert "warfarin" in documented[0].lower()
    assert any(alert["severity"] == "major" for alert in review["interaction_alerts"])


def test_report_values_from_the_visit_note_reach_the_lab_gates():
    review = medication_review_for_encounter(
        "known diabetes and hypertension",
        "eGFR 26. Potassium 6.1 mmol/L.",
        patient=_visit(conditions=["diabetes", "hypertension"]),
    )
    assert _blocked(review, "metformin") is not None
    assert _blocked(review, "ramipril") is not None or _blocked(review, "losartan") is not None


# ---------------------------------------------------------------------------
# Line by line: later lines add, never replace, and a clear resets
# ---------------------------------------------------------------------------

def test_each_new_line_can_change_the_screen():
    first = medication_review_for_encounter("crushing chest pain since an hour", patient=_visit())
    assert _rec(first, "aspirin") is not None
    assert first["pathway"]["urgency"] == "emergency"

    second = medication_review_for_encounter(
        "crushing chest pain since an hour\nI am allergic to aspirin",
        patient=_visit(),
    )
    assert _rec(second, "aspirin") is None
    assert _allergy_alert(second, "aspirin") is not None


def test_accumulated_lines_keep_the_earlier_findings():
    first_line = medication_review_for_encounter("crushing chest pain radiating to the left arm", patient=_visit())
    assert _rec(first_line, "aspirin") is not None

    later = medication_review_for_encounter(
        "crushing chest pain radiating to the left arm\nI had a stroke last year and I take clopidogrel",
        patient=_visit(),
    )
    indications = {item["name"] for item in later["indications"]}
    assert "suspected_acs" in indications  # the first line is still accounted for
    assert "cerebrovascular_disease" in later["patient_profile"]["conditions"]
    assert any(entry.startswith("clopidogrel") for entry in later["patient_profile"]["current_medications"])


def test_cleared_transcript_leaves_no_stale_findings():
    spoken = medication_review_for_encounter(
        "crushing chest pain; I am allergic to aspirin and take warfarin", patient=_visit()
    )
    assert spoken["allergy_alerts"]
    assert spoken["interaction_alerts"]

    cleared = medication_review_for_encounter(
        "", "", patient={"age": "", "sex": "", "conditions": [], "allergies": []}
    )
    assert cleared["allergy_alerts"] == []
    assert cleared["interaction_alerts"] == []
    assert cleared["recommendations"] == []


def test_gaps_are_reported_instead_of_assumed():
    review = medication_review_for_encounter("chest pain", patient={})
    missing = " ".join(review["missing_information"]).lower()
    assert "allerg" in missing
    assert "age" in missing or "medication" in missing


def test_context_builder_does_not_mutate_the_caller_payload():
    payload = {"conditions": ["hypertension"], "allergies": ["aspirin"], "current_medications": []}
    context = build_medication_context("takes warfarin, allergic to ibuprofen", "", payload)
    assert payload["conditions"] == ["hypertension"]
    assert payload["allergies"] == ["aspirin"]
    assert payload["current_medications"] == []
    assert "ibuprofen" in context["allergies"]
    assert any("warfarin" in name for name in context["current_medications"])


# ---------------------------------------------------------------------------
# The socket frame carries it
# ---------------------------------------------------------------------------

def test_analysis_frame_carries_the_medication_review():
    """The copilot frame must ship the review, built from the visit details.

    The LLM tier is stubbed out: this asserts the wiring (encounter text +
    visit details + frame field), not the model.
    """
    original_translate = realtime_service.translate_to_english
    original_plan = realtime_service.generate_ai_copilot_plan
    realtime_service.translate_to_english = lambda text, language_hint="en-US": text
    realtime_service.generate_ai_copilot_plan = lambda **kwargs: {
        "doctor_questions": [],
        "recommended_tests": ["12-lead ECG"],
        "next_steps": [],
        "diagnostic_impression": ["…"],
        "urgency": "high",
        "safety_note": "Decision support only.",
    }
    try:
        payload = process_live_transcript_entry(
            text="and I am allergic to aspirin",
            speaker="patient",
            patient=_visit(),
            transcript="crushing chest pain since an hour",
        )
    finally:
        realtime_service.translate_to_english = original_translate
        realtime_service.generate_ai_copilot_plan = original_plan

    review = payload["medication_review"]
    assert _allergy_alert(review, "aspirin") is not None  # this line
    assert _rec(review, "aspirin") is None
    assert "suspected_acs" in {item["name"] for item in review["indications"]}  # earlier line
    assert review["extracted"]["entities"] is not None
    assert "Decision support only" in review["disclaimer"]


def main() -> None:
    """Run the suite directly (no pytest needed)."""
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_") and callable(fn)]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"[PASS] {name}")
        except AssertionError as exc:
            failures.append(name)
            print(f"[FAIL] {name}: {exc}")
    if failures:
        print(f"\n{len(failures)} failure(s): {', '.join(failures)}")
        sys.exit(1)
    print(f"\nAll {len(tests)} live medication cases passed.")


if __name__ == "__main__":
    main()
