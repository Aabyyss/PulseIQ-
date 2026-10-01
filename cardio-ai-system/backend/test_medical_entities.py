"""Medical entity extraction & SOAP note (Area 4 of the review)."""

from backend.medical_entities import (
    build_soap_note,
    extract_durations,
    extract_entities,
    extract_medications,
    extract_risk_factors,
)


def test_medications_with_dose():
    meds = extract_medications("On aspirin 75 mg and atorvastatin 20 mg daily")
    names = {m["name"] for m in meds}
    assert {"aspirin", "atorvastatin"} <= names
    aspirin = next(m for m in meds if m["name"] == "aspirin")
    assert aspirin["dose_mg"] == "75"


def test_negated_medication_not_extracted():
    assert extract_medications("No aspirin or clopidogrel today") == []


def test_durations_extracted():
    durations = extract_durations("Chest pain for 3 days, each episode lasts 20 minutes")
    assert any("3" in d and "day" in d for d in durations)
    assert any("20" in d and "minute" in d for d in durations)


def test_duration_since_form():
    durations = extract_durations("Symptoms since yesterday morning")
    assert any("yesterday" in d for d in durations)


def test_risk_factors_present():
    factors = extract_risk_factors("He is diabetic with hypertension and smokes")
    assert "diabetes" in factors
    assert "hypertension" in factors
    assert "smoking" in factors


def test_negated_risk_factors_skipped():
    factors = extract_risk_factors("No diabetes, denies smoking, not hypertensive")
    assert "diabetes" not in factors
    assert "smoking" not in factors
    assert "hypertension" not in factors


def test_entities_all_classes():
    entities = extract_entities(
        "60M, chest pain for 2 days, on metformin 500 mg, diabetic, "
        "each episode 10 minutes on walking"
    )
    assert entities["medications"]
    assert entities["durations"]
    assert "diabetes" in entities["risk_factors"]


def test_soap_note_structure():
    note = build_soap_note(
        transcript="Chest pain for 2 days, on aspirin 75 mg, diabetic. Each episode 10 minutes on walking.",
        symptoms=["chest pain", "fatigue"],
        report_text="LDL 168 mg/dL",
        risk_level="Medium",
    )
    assert set(note) >= {"subjective", "objective", "assessment", "plan", "entities"}
    joined_s = " ".join(note["subjective"])
    assert "chest pain" in joined_s
    assert "aspirin" in joined_s
    assert "2" in joined_s  # duration carried through
    joined_o = " ".join(note["objective"])
    assert "diabetes" in joined_o
    assert "LDL 168" in joined_o
    assert "Medium" in note["assessment"][0]
    # honesty markers
    assert "not a diagnosis" in note["assessment"][0].lower()


def test_soap_note_empty_encounter_is_honest():
    note = build_soap_note(transcript="", symptoms=[], report_text="")
    assert any("No symptom" in s for s in note["subjective"])
    assert any("No report" in o for o in note["objective"])
    # must not invent findings
    assert not note["entities"]["medications"]
    assert not note["entities"]["risk_factors"]
