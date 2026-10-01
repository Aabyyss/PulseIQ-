"""De-identification tests (Area 1 of the improvement review).

CNIC/phone/email removal, idempotency, and — the important one — that
clinical text (labs, doses, symptoms) is never touched.
"""

from backend.deidentify import deidentify, deidentify_transcript


def test_cnic_dashed_removed():
    text, counts = deidentify("Patient CNIC 35202-1234567-1 reported chest pain")
    assert "35202-1234567-1" not in text
    assert "[REDACTED CNIC]" in text
    assert counts.get("cnic") == 1
    assert "chest pain" in text  # clinical text survives


def test_cnic_undashed_13_digit_removed():
    text, counts = deidentify("CNIC 3520212345671 on file")
    assert "3520212345671" not in text
    assert counts.get("cnic") == 1


def test_pakistani_mobile_removed():
    for variant in ("0300-1234567", "0321 1234567", "+92 333 1234567", "923001234567"):
        text, counts = deidentify(f"Call me on {variant} about my angina")
        assert variant not in text, variant
        assert counts.get("phone") == 1, variant
        assert "angina" in text


def test_email_removed():
    text, counts = deidentify("Send reports to ali.khan@example.com please")
    assert "example.com" not in text.split("@")[-1] or "@" not in text
    assert "[REDACTED EMAIL]" in text
    assert counts.get("email") == 1


def test_labeled_name_removed():
    text, counts = deidentify("Patient name: Ali Khan reported palpitations")
    assert "Ali Khan" not in text
    assert "[REDACTED NAME]" in text
    assert counts.get("name") == 1
    # The label stays so the record still reads naturally.
    assert "Patient name:" in text


def test_honorific_name_removed():
    text, counts = deidentify("Mr. Ali Khan is seen for hypertension follow up")
    assert "Ali Khan" not in text
    assert "[REDACTED NAME]" in text
    assert "hypertension" in text


def test_clinical_capitals_never_redacted():
    # Capitalised clinical terms must survive: no bare-capital redaction.
    text, counts = deidentify(
        "Anterior ST Elevation with Troponin elevation on ECG and raised LDL"
    )
    assert "Anterior" in text and "Troponin" in text and "ECG" in text
    assert "name" not in counts


def test_lab_values_and_doses_survive():
    text, counts = deidentify(
        "Troponin I 0.08 ng/mL, potassium 6.1 mmol/L, give 300 mg aspirin"
    )
    assert "0.08" in text and "6.1" in text and "300 mg" in text
    assert counts == {}


def test_idempotent_second_run_is_noop():
    once, counts1 = deidentify("Call 0300-1234567 about CNIC 35202-1234567-1")
    twice, counts2 = deidentify(once)
    assert once == twice
    assert counts2 == {}
    assert counts1.get("phone") == 1 and counts1.get("cnic") == 1


def test_empty_input():
    assert deidentify("") == ("", {})


def test_deidentify_transcript_lines():
    lines = [
        {"speaker": "patient", "text": "My number is 0300-1234567, chest pain started 2 days ago"},
        {"speaker": "doctor", "text": "Start aspirin 75 mg daily"},
        "not-a-dict",
    ]
    cleaned = deidentify_transcript(lines)
    assert "[REDACTED PHONE]" in cleaned[0]["text"]
    assert "chest pain" in cleaned[0]["text"]
    assert cleaned[1]["text"] == "Start aspirin 75 mg daily"
    assert cleaned[2] == "not-a-dict"
    # input untouched
    assert "0300-1234567" in lines[0]["text"]
