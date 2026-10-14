"""Live medication safety screen — the review the copilot recomputes per line.

Every case asserts a clinical direction on the *live* path: the visit details
the clinician recorded must count, an allergy said out loud must block with the
form left empty, a later line must add to the screen instead of replacing it,
and a cleared transcript must leave nothing stale behind. Runnable via pytest
and directly (``python backend/test_live_medication_review.py``).
"""

import os
import sys
import tempfile
import time
from uuid import uuid4

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Throwaway database for the socket case (kept if another test module already
# pointed the account store at one, so a full pytest run shares it).
os.environ.setdefault(
    "PULSEIQ_DB", os.path.join(tempfile.mkdtemp(prefix="pulseiq-ws-test-"), "test.db")
)

from backend import auth_store, realtime_service  # noqa: E402
from backend.api_server import app as api_app  # noqa: E402
from backend.encounter_context import build_medication_context  # noqa: E402
from backend.realtime_service import (  # noqa: E402
    medication_review_for_encounter,
    medication_review_for_live_line,
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

def test_the_recorded_group_reaches_the_live_screen_and_its_score_block():
    """The group the consultation form records has to survive the per-line rebuild.

    The live screen is recomputed from the visit header on every line, so a field
    the header carries but the rebuild drops would leave the live scores on the
    fallback model while the medication form scored the recorded one — two
    readings of the same visit. An unrecorded group keeps the reported fallback.
    """
    text = "routine risk review, non-smoker, no diabetes"
    lipids = {"total_cholesterol": 213, "hdl": 50}

    recorded = medication_review_for_encounter(
        text, patient=_visit(race="white", labs=lipids, vitals={"systolic_bp": 120})
    )
    assert recorded["risk_scores"]["inputs"]["race"] == "white"
    assert recorded["risk_scores"]["ascvd"]["group"] == "white men"

    line = medication_review_for_live_line(
        text=text, patient=_visit(race="white", labs=lipids, vitals={"systolic_bp": 120})
    )
    assert line["risk_scores"]["ascvd"]["group"] == "white men"

    unrecorded = medication_review_for_encounter(text, patient=_visit(labs=lipids, vitals={"systolic_bp": 120}))
    assert unrecorded["risk_scores"]["ascvd"]["race_captured"] is False
    assert unrecorded["risk_scores"]["inputs"]["race"] is None


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


def test_a_lab_value_read_aloud_reaches_the_lab_gates():
    """Reading "eGFR 26" off the note out loud is the same fact as pasting it."""
    review = medication_review_for_live_line(
        "the report says his eGFR is 26 and he has diabetes", patient=_visit()
    )
    assert _blocked(review, "metformin") is not None
    assert review["patient_profile"]["labs_considered"].get("renal_severe") is not None


def test_a_recorded_lab_still_wins_over_the_spoken_one():
    review = medication_review_for_live_line(
        "the report says eGFR 26",
        patient=_visit(conditions=["diabetes"], labs={"egfr": 58}),
    )
    assert review["patient_profile"]["labs_considered"]["renal_impairment"] == 58
    assert review["patient_profile"]["labs_considered"].get("renal_severe") is None


def test_the_written_report_wins_over_the_spoken_value():
    review = medication_review_for_live_line(
        "she mentioned an eGFR of 26",
        report_text="eGFR 58 mL/min",
        patient=_visit(conditions=["diabetes"]),
    )
    assert review["patient_profile"]["labs_considered"]["renal_impairment"] == 58
    assert review["patient_profile"]["labs_considered"].get("renal_severe") is None


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
# The instant ack carries it, before any model call
# ---------------------------------------------------------------------------

def test_ack_snapshot_blocks_on_the_line_that_reported_it():
    """The safety screen must not wait for the copilot plan (tens of seconds)."""
    first = medication_review_for_live_line(
        "he is having crushing chest pain since an hour", patient=_visit()
    )
    assert _rec(first, "aspirin") is not None
    assert first["pathway"]["urgency"] == "emergency"  # no risk band needed

    second = medication_review_for_live_line(
        "I am allergic to aspirin",
        transcript="he is having crushing chest pain since an hour",
        patient=_visit(),
    )
    assert _allergy_alert(second, "aspirin") is not None
    assert _rec(second, "aspirin") is None
    assert "suspected_acs" in {item["name"] for item in second["indications"]}


def test_ack_snapshot_uses_the_current_lines_symptoms():
    """The caller passes the ack's own extraction, so learned phrases count too."""
    review = medication_review_for_live_line(
        "and the pain is crushing", patient=_visit(), symptoms=["chest pain"]
    )
    assert "suspected_acs" in {item["name"] for item in review["indications"]}
    assert review["pathway"]["urgency"] == "emergency"


def test_ack_snapshot_agrees_with_the_analysis_frame_on_the_safety_findings():
    """Early and late reviews may differ in wording, never in what they block."""
    line = "I am allergic to aspirin and I take warfarin 5 mg daily"
    prior = "he is having crushing chest pain since an hour"
    early = medication_review_for_live_line(line, transcript=prior, patient=_visit())
    late = medication_review_for_encounter(f"{prior}\n{line}", "", patient=_visit())

    assert {a["drug"] for a in early["allergy_alerts"]} == {a["drug"] for a in late["allergy_alerts"]}
    assert {c["drug"] for c in early["contraindicated"]} == {c["drug"] for c in late["contraindicated"]}
    assert {tuple(i["pair"]) for i in early["interaction_alerts"]} == {
        tuple(i["pair"]) for i in late["interaction_alerts"]
    }
    assert early["pathway"]["urgency"] == late["pathway"]["urgency"]


def test_a_medication_named_in_the_same_breath_is_not_an_allergy():
    """One sentence, two roles: the allergy blocks, the medication interacts.

    The allergy phrase used to swallow the rest of the clause, so "allergic to
    aspirin and he takes warfarin" reported warfarin as a *reported allergy* —
    blocking a drug the patient actually takes.
    """
    review = medication_review_for_live_line(
        "he is allergic to aspirin and he takes warfarin 5 mg daily",
        transcript="he is having crushing chest pain since an hour",
        patient=_visit(),
    )
    assert "aspirin" in review["extracted"]["allergies_from_text"]
    assert all(
        "warfarin" not in term.lower() for term in review["extracted"]["allergies_from_text"]
    ), "the medication from the same sentence was recorded as an allergy"
    assert not any("warfarin" in a["drug"].lower() for a in review["allergy_alerts"])
    assert any("warfarin" in name.lower() for name in review["patient_profile"]["current_medications"])
    assert any(alert["severity"] == "major" for alert in review["interaction_alerts"])


def test_two_substances_in_one_allergy_clause_are_both_kept():
    review = medication_review_for_live_line("allergic to aspirin and sulfa", patient=_visit())
    terms = " ".join(review["extracted"]["allergies_from_text"]).lower()
    assert "aspirin" in terms
    assert "sulfa" in terms


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


def _socket_token() -> str:
    """A signed-in clinician for the socket case (throwaway account)."""
    user = auth_store.create_user(
        f"live-ws-{uuid4().hex[:10]}@cardio.local", "ws-test-pass-1234", "Live WS Test"
    )
    return auth_store.issue_token(user["id"])


def test_a_line_ack_never_waits_for_the_previous_lines_plan():
    """The safety screen must not queue behind the model — that is its point.

    Both lines are acked in a fraction of a second even though the copilot plan
    for each one sleeps for seconds: the plan runs on a worker while the
    receiving loop keeps serving acks. The old inline await made the second
    ack wait for the first plan, which is exactly what a clinician speaking
    every few seconds would have felt.
    """
    from fastapi.testclient import TestClient

    original_plan = realtime_service.generate_ai_copilot_plan
    original_translate = realtime_service.translate_to_english
    realtime_service.translate_to_english = lambda text, language_hint="en-US": text

    def slow_plan(**kwargs):
        time.sleep(2.0)
        return {
            "doctor_questions": [],
            "recommended_tests": ["12-lead ECG"],
            "next_steps": [],
            "diagnostic_impression": ["…"],
            "urgency": "high",
            "safety_note": "Decision support only.",
        }

    realtime_service.generate_ai_copilot_plan = slow_plan
    token = _socket_token()
    first_line = "he is having crushing chest pain since an hour"
    try:
        with TestClient(api_app) as client:
            with client.websocket_connect(f"/ws/consultation?token={token}") as socket:
                socket.send_json({"speaker": "patient", "text": first_line, "patient": _visit()})
                first_ack = socket.receive_json()
                assert first_ack["kind"] == "line_ack"
                assert first_ack["line_seq"] == 1  # the first line on this connection

                started = time.monotonic()
                socket.send_json(
                    {
                        "speaker": "patient",
                        "text": "I am allergic to aspirin",
                        "transcript": first_line,
                        "patient": _visit(),
                    }
                )
                # Read until the second line is acked, timing that ack: with the
                # plan awaited inline it arrives only after the plan (seconds
                # later), behind the first line's analysis frame.
                ack = None
                elapsed = None
                analyses: list[dict] = []
                for _ in range(8):
                    frame = socket.receive_json()
                    if frame.get("kind") == "line_ack":
                        if ack is None:
                            ack, elapsed = frame, time.monotonic() - started
                        continue
                    assert frame.get("kind") == "analysis", frame
                    analyses.append(frame)
                    if ack is not None and len(analyses) == 2:
                        break

                assert ack is not None, "the second line was never acked"
                assert ack["line_seq"] == 2  # both frames name the line they describe
                assert elapsed is not None and elapsed < 1.0, (
                    f"the ack waited {elapsed:.1f}s on the previous line's plan"
                )
                assert _allergy_alert(ack["medication_review"], "aspirin") is not None
                assert _rec(ack["medication_review"], "aspirin") is None
                # Both plans still arrive, numbered in the order the lines were
                # spoken — which is how a late plan is recognised as late.
                assert len(analyses) == 2
                assert [frame["line_seq"] for frame in analyses] == [1, 2]
                assert "crushing chest pain" in analyses[0]["transcript"]
                assert "allergic to aspirin" in analyses[1]["transcript"]
    finally:
        realtime_service.generate_ai_copilot_plan = original_plan
        realtime_service.translate_to_english = original_translate


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
