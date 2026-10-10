"""FHIR export — the structured findings, asserted as an EHR-shaped Bundle.

Every case asserts something an EHR (or a reviewer) would rely on: the bundle
is internally referentially complete, the patient and the problems are present,
laboratory values keep their units and interpretation, reported allergies and
current medications become the right resources, the medication safety findings
carry severity and mitigation, and nothing is coded that this codebase has no
curated code for. Runnable via pytest and directly
(``python backend/test_fhir_export.py``).
"""

import base64
import json
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend import api_server  # noqa: E402
from backend.fhir_export import SNOMED_SYSTEM, build_fhir_bundle  # noqa: E402

PAYLOAD = {
    "patient_name": "Demo Patient",
    "patient_age": "68",
    "patient_gender": "Male",
    "visit_date": "2026-10-11",
    "doctor_name": "Dr. Demo",
    "chief_complaint": "crushing chest pain",
    "text": "crushing chest pain radiating to the left arm for an hour, sweaty",
    "report_text": "Troponin I: 0.09 ng/mL. Potassium 6.1 mmol/L. eGFR 26.",
    "risk_level": "High",
    "symptom_notes": ["chest pain", "sweating"],
    "conditions": ["hypertension", "prior MI"],
    "allergies": ["aspirin"],
    "current_medications": ["warfarin 5 mg", "metoprolol 25 mg"],
}


def _resources(result: dict, resource_type: str) -> list[dict]:
    return [
        entry["resource"]
        for entry in result["bundle"]["entry"]
        if entry["resource"]["resourceType"] == resource_type
    ]


def _by_code(resources: list[dict], needle: str) -> list[dict]:
    found = []
    for resource in resources:
        concept = resource.get("code") or resource.get("medicationCodeableConcept") or {}
        haystack = " ".join(
            [str(concept.get("text", ""))]
            + [str(coding.get("display", "")) for coding in concept.get("coding", [])]
        ).lower()
        if needle.lower() in haystack:
            found.append(resource)
    return found


# ---------------------------------------------------------------------------
# Structural integrity — what makes it a Bundle rather than a JSON dump
# ---------------------------------------------------------------------------

def test_bundle_is_a_fhir_collection_with_resolvable_references():
    result = build_fhir_bundle(PAYLOAD)
    bundle = result["bundle"]
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "collection"
    assert bundle["timestamp"]
    assert len(bundle["entry"]) >= 8
    full_urls = {entry["fullUrl"] for entry in bundle["entry"]}
    ids = [entry["resource"]["id"] for entry in bundle["entry"]]
    assert len(ids) == len(set(ids)), "resource ids must be unique"
    for entry in bundle["entry"]:
        assert entry["fullUrl"] == f"urn:uuid:{entry['resource']['id']}"
        for reference in _references(entry["resource"]):
            assert reference in full_urls, f"dangling reference {reference}"


def _references(node) -> list[str]:
    """Every Reference.reference in a resource (FHIR references are nested)."""
    found: list[str] = []
    if isinstance(node, dict):
        if set(node.keys()) == {"reference"} and isinstance(node.get("reference"), str):
            found.append(node["reference"])
        for value in node.values():
            found.extend(_references(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_references(item))
    return found


def test_bundle_is_json_serialisable_and_carries_the_export_tag():
    result = build_fhir_bundle(PAYLOAD)
    dumped = json.loads(json.dumps(result["bundle"]))
    assert dumped["meta"]["tag"][0]["code"] == "pulseiq-export"
    patient = _resources(result, "Patient")[0]
    assert patient["meta"]["tag"][0]["system"] == "urn:pulseiq:source"


def test_each_export_gets_fresh_ids_but_the_same_content():
    first = build_fhir_bundle(PAYLOAD)
    second = build_fhir_bundle(PAYLOAD)
    assert first["bundle"]["id"] != second["bundle"]["id"]
    assert first["resource_counts"] == second["resource_counts"]
    first_conditions = {c["code"]["text"] for c in _resources(first, "Condition")}
    second_conditions = {c["code"]["text"] for c in _resources(second, "Condition")}
    assert first_conditions == second_conditions


# ---------------------------------------------------------------------------
# Patient
# ---------------------------------------------------------------------------

def test_patient_carries_name_gender_and_the_year_derived_from_age():
    result = build_fhir_bundle(PAYLOAD)
    patient = _resources(result, "Patient")[0]
    assert patient["name"][0]["text"] == "Demo Patient"
    assert patient["gender"] == "male"
    assert patient["birthDate"] == str(__import__("datetime").datetime.now().year - 68)
    assert any("birthDate" in caveat for caveat in result["caveats"])


def test_missing_age_and_name_are_reported_instead_of_invented():
    result = build_fhir_bundle({"text": "chest pain", "conditions": ["hypertension"]})
    patient = _resources(result, "Patient")[0]
    assert "birthDate" not in patient
    assert "name" not in patient
    assert patient["gender"] == "unknown"
    gaps = " ".join(result["missing_information"]).lower()
    assert "age" in gaps and "name" in gaps


def test_an_unrecognised_gender_string_is_flagged_rather_than_silently_mapped():
    result = build_fhir_bundle({"text": "chest pain", "patient_gender": "not stated"})
    assert _resources(result, "Patient")[0]["gender"] == "unknown"
    assert any("gender" in caveat.lower() for caveat in result["caveats"])


# ---------------------------------------------------------------------------
# Conditions — the problem list
# ---------------------------------------------------------------------------

def test_recorded_history_becomes_one_condition_per_canonical_problem():
    result = build_fhir_bundle(PAYLOAD)
    conditions = _resources(result, "Condition")
    labels = [condition["code"]["text"] for condition in conditions]
    assert "Hypertension" in labels
    assert "Previous myocardial infarction" in labels
    # "prior MI" is both the free text typed and a canonical tag — it must not
    # appear twice under two names.
    assert labels.count("Previous myocardial infarction") == 1
    assert not any("prior MI" == label for label in labels)
    for condition in conditions:
        assert condition["subject"]["reference"].startswith("urn:uuid:")
        assert condition["encounter"]["reference"].startswith("urn:uuid:")
        assert condition["category"][0]["coding"][0]["code"] == "problem-list-item"


def test_free_text_history_is_exported_as_written_and_flagged_as_uncoded():
    result = build_fhir_bundle({"text": "", "conditions": ["stent 2023"]})
    # the condition vocabulary recognises "stent" as a canonical problem
    labels = [condition["code"]["text"] for condition in _resources(result, "Condition")]
    assert "Previous PCI or CABG" in labels
    plain = build_fhir_bundle({"text": "", "conditions": ["marfanoid habitus"]})
    plain_labels = [condition["code"]["text"] for condition in _resources(plain, "Condition")]
    assert "marfanoid habitus" in plain_labels
    assert any("free text" in gap for gap in plain["missing_information"])


def test_reported_symptoms_are_provisional_conditions_with_curated_snomed_codes():
    result = build_fhir_bundle(PAYLOAD)
    chest_pain = _by_code(_resources(result, "Condition"), "chest pain")[0]
    assert chest_pain["verificationStatus"]["coding"][0]["code"] == "provisional"
    codings = chest_pain["code"]["coding"]
    snomed = [coding for coding in codings if coding["system"] == SNOMED_SYSTEM]
    assert snomed and snomed[0]["code"] == "29857009"
    assert "not a diagnosis" in chest_pain["note"][0]["text"]


def test_no_terminology_is_invented_for_history_conditions():
    result = build_fhir_bundle(PAYLOAD)
    for condition in _resources(result, "Condition"):
        if condition["verificationStatus"]["coding"][0]["code"] == "unconfirmed":
            assert "coding" not in condition["code"], "history terms must not carry guessed codes"


# ---------------------------------------------------------------------------
# Observations — laboratory values and the screening band
# ---------------------------------------------------------------------------

def test_laboratory_values_keep_their_quantity_unit_and_interpretation():
    result = build_fhir_bundle(PAYLOAD)
    observations = _resources(result, "Observation")
    potassium = _by_code(observations, "potassium")[0]
    assert potassium["status"] == "final"
    assert potassium["category"][0]["coding"][0]["code"] == "laboratory"
    assert potassium["valueQuantity"]["value"] == 6.1
    assert potassium["valueQuantity"]["unit"] == "mmol/l"
    assert potassium["interpretation"][0]["coding"][0]["code"] == "HH"
    assert potassium["referenceRange"][0]["text"]
    assert potassium["subject"]["reference"].startswith("urn:uuid:")
    troponin = _by_code(observations, "troponin")[0]
    assert troponin["valueQuantity"]["value"] == 0.09


def test_units_are_exported_as_text_without_a_guessed_ucum_code():
    result = build_fhir_bundle(PAYLOAD)
    for observation in _resources(result, "Observation"):
        quantity = observation.get("valueQuantity")
        if quantity:
            assert "system" not in quantity and "code" not in quantity


def test_the_risk_band_is_exported_as_a_labelled_decision_support_observation():
    result = build_fhir_bundle(PAYLOAD)
    survey = [
        observation
        for observation in _resources(result, "Observation")
        if observation["category"][0]["coding"][0]["code"] == "survey"
    ][0]
    assert survey["valueString"] == "High"
    assert "decision-support" in survey["code"]["text"].lower()
    assert "not a diagnosis" in survey["note"][0]["text"]


def test_no_report_text_means_no_laboratory_observations_and_a_reported_gap():
    result = build_fhir_bundle({"text": "chest pain", "risk_level": "Medium"})
    assert not [
        observation
        for observation in _resources(result, "Observation")
        if observation["category"][0]["coding"][0]["code"] == "laboratory"
    ]
    assert any("laboratory" in gap.lower() for gap in result["missing_information"])


# ---------------------------------------------------------------------------
# Allergies and medications
# ---------------------------------------------------------------------------

def test_reported_allergy_becomes_an_allergy_intolerance():
    result = build_fhir_bundle(PAYLOAD)
    allergies = _resources(result, "AllergyIntolerance")
    assert [item for item in allergies if item["code"]["text"] == "aspirin"]
    assert allergies[0]["patient"]["reference"].startswith("urn:uuid:")
    assert allergies[0]["category"] == ["medication"]


def test_placeholders_for_no_allergy_never_become_allergy_records():
    for placeholder in ("none", "none recorded", "NKDA", "no known drug allergies"):
        result = build_fhir_bundle({"text": "chest pain", "allergies": [placeholder]})
        assert _resources(result, "AllergyIntolerance") == [], placeholder
        assert any("allergy" in gap.lower() for gap in result["missing_information"])


def test_current_medications_become_active_medication_statements():
    result = build_fhir_bundle(PAYLOAD)
    statements = _resources(result, "MedicationStatement")
    texts = [item["medicationCodeableConcept"]["text"] for item in statements]
    assert "warfarin 5 mg" in texts
    assert all(item["status"] == "active" for item in statements)


# ---------------------------------------------------------------------------
# The medication safety review, as DetectedIssue resources
# ---------------------------------------------------------------------------

def test_allergy_conflict_is_a_high_severity_issue_with_its_alternative():
    result = build_fhir_bundle(PAYLOAD)
    issues = _resources(result, "DetectedIssue")
    allergy_issues = [issue for issue in issues if "allergy conflict" in issue["code"]["text"].lower()]
    assert allergy_issues
    assert allergy_issues[0]["severity"] == "high"
    assert allergy_issues[0]["status"] == "preliminary"
    assert "aspirin" in allergy_issues[0]["detail"].lower()
    assert allergy_issues[0]["mitigation"][0]["action"]["text"]


def test_renal_contraindication_and_interaction_are_reported_with_severity():
    # Diabetes is the indication that brings metformin into consideration at all;
    # only a considered drug can be reported as blocked.
    result = build_fhir_bundle(dict(PAYLOAD, conditions=["hypertension", "prior MI", "diabetes"]))
    issues = _resources(result, "DetectedIssue")
    metformin = [issue for issue in issues if "metformin" in json.dumps(issue).lower()]
    assert metformin, "eGFR 26 with diabetes should block metformin"
    assert metformin[0]["severity"] == "high"
    assert "egfr" in metformin[0]["detail"].lower()
    interactions = [issue for issue in issues if "interaction" in issue["code"]["text"].lower()]
    assert interactions, "warfarin plus a recommended antiplatelet is an interaction"
    assert interactions[0]["implicated"], "an interaction names the drugs that pair"
    assert all(issue["severity"] in ("high", "moderate") for issue in issues)


# ---------------------------------------------------------------------------
# DocumentReference — the consultation document
# ---------------------------------------------------------------------------

def test_document_reference_carries_a_readable_note_when_no_report_is_given():
    result = build_fhir_bundle(PAYLOAD)
    document = _resources(result, "DocumentReference")[0]
    assert document["status"] == "current"
    attachment = document["content"][0]["attachment"]
    assert attachment["contentType"].startswith("text/plain")
    text = base64.b64decode(attachment["data"]).decode("utf-8")
    assert "Subjective" in text and "Assessment" in text
    assert attachment["size"] == len(text.encode("utf-8"))


def test_a_supplied_final_report_is_what_gets_documented():
    payload = dict(PAYLOAD, report={
        "title": "Consultation Report",
        "summary": "Stable exertional angina.",
        "probable_diagnosis": ["Stable angina"],
        "doctor_advice": ["Continue antiplatelet therapy"],
        "medical_treatment_plan": ["Titrate statin"],
        "follow_up_plan": ["Review in 4 weeks"],
        "red_flags": ["Rest pain"],
    })
    result = build_fhir_bundle(payload)
    text = base64.b64decode(_resources(result, "DocumentReference")[0]["content"][0]["attachment"]["data"]).decode("utf-8")
    assert "Stable exertional angina." in text
    assert "Titrate statin" in text
    assert "Subjective" not in text


def test_the_export_carries_findings_not_the_transcript():
    payload = dict(PAYLOAD, text="my neighbour saw me collapse at the bus stop, crushing chest pain")
    result = build_fhir_bundle(payload)
    document = base64.b64decode(
        _resources(result, "DocumentReference")[0]["content"][0]["attachment"]["data"]
    ).decode("utf-8")
    assert "neighbour saw me collapse" not in document
    assert "chest pain" in document.lower()


def test_the_disclaimer_travels_with_every_export():
    result = build_fhir_bundle(PAYLOAD)
    assert "Decision-support" in result["disclaimer"]
    assert result["fhir_version"] == "4.0.1"
    assert result["resource_counts"]["Patient"] == 1


# ---------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------

def test_endpoint_rejects_an_empty_request_and_returns_a_bundle_otherwise():
    assert api_server.fhir_export({}, user={"id": 1}) == {"error": "text, report_text or patient context is required"}
    result = api_server.fhir_export({"text": "chest pain"}, user={"id": 1})
    assert result["bundle"]["resourceType"] == "Bundle"
    assert result["bundle"]["entry"]


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
    print(f"\nAll {len(tests)} FHIR export cases passed.")


if __name__ == "__main__":
    main()
