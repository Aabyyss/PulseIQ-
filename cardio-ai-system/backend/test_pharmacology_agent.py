"""Medication recommendation & safety review — directional clinical tests.

Every case asserts a *clinical direction*, not a shape: an allergy must block
the drug, renal failure must block metformin, hyperkalaemia must block RAAS
blockade, and facts that were never supplied must be reported as missing
instead of assumed. Runnable via pytest and directly
(``python backend/test_pharmacology_agent.py``).
"""

import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.pharmacology_agent import (  # noqa: E402
    allergy_matches,
    current_med_keys,
    detect_conditions,
    extract_allergy_mentions,
    lab_tags,
    review_medications,
)
from backend.orchestrator import run_medication_review  # noqa: E402


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


# ---------------------------------------------------------------------------
# Presentation → options
# ---------------------------------------------------------------------------

def test_suspected_acs_offers_aspirin_and_escalates_pathway():
    review = review_medications(
        symptoms=["chest pain", "sweating"],
        age=58,
        risk_level="High",
        allergies=["none"],
    )
    aspirin = _rec(review, "aspirin")
    assert aspirin is not None
    assert any("chest pain" in reason for reason in aspirin["triggered_by"])
    assert review["pathway"]["urgency"] == "emergency"


def test_statin_is_attached_to_established_cad_not_only_to_chest_pain():
    review = review_medications(conditions=["prior MI", "dyslipidaemia"], risk_level="Low")
    statin = _rec(review, "statin")
    assert statin is not None
    assert "prior_mi" in statin["indications"]
    assert any("myocardial infarction" in r for r in statin["triggered_by"])


def test_no_captured_indication_yields_no_recommendations():
    review = review_medications(symptoms=["cough"], conditions=[], age=30)
    assert review["recommendations"] == []
    assert review["contraindicated"] == []
    assert "No captured fact triggers" in review["summary"]


def test_secondary_prevention_gap_is_named_for_post_pci_patient():
    review = review_medications(conditions=["stent 2024"], current_medications=["aspirin 75 mg"])
    assert _rec(review, "aspirin")["status"] == "already-documented"
    statin = _rec(review, "statin")  # the secondary-prevention gap is named, not left silent
    assert statin is not None and statin["status"] == "recommended"
    assert any("PCI" in reason or "stent" in reason for reason in statin["triggered_by"])


# ---------------------------------------------------------------------------
# Allergies
# ---------------------------------------------------------------------------

def test_reported_allergy_blocks_aspirin_and_offers_an_alternative():
    review = review_medications(
        symptoms=["chest pain"],
        allergies=["aspirin"],
        age=60,
        risk_level="Medium",
    )
    assert _rec(review, "aspirin") is None
    blocked = _blocked(review, "aspirin")
    assert blocked is not None
    assert blocked["blocks"][0]["kind"] == "allergy"
    assert blocked["severity"] == "absolute"
    alert = review["allergy_alerts"][0]
    assert "aspirin" in alert["matched_terms"]
    assert "P2Y12" in alert["alternative"]


def test_class_level_allergy_matches_the_class_member():
    assert allergy_matches("NSAIDs", {"allergens": ["aspirin", "nsaid", "nsaids"]})
    review = review_medications(
        symptoms=["chest pain"], allergies=["nsaids", "statin"], age=64, risk_level="High"
    )
    assert _rec(review, "aspirin") is None
    assert _rec(review, "statin") is None


def test_allergy_phrases_are_read_from_the_narrative():
    mentions = extract_allergy_mentions("He is allergic to aspirin and sulfa drugs. NKDA elsewhere.")
    joined = " ".join(mentions).lower()
    assert "aspirin" in joined
    # "no known drug allergies" must not invent a substance
    assert extract_allergy_mentions("No known drug allergies") == []


def test_sulfonamide_history_flags_furosemide_without_blocking_it():
    review = review_medications(
        symptoms=["leg swelling", "shortness of breath"],
        allergies=["sulfa"],
        conditions=["heart failure"],
        age=70,
    )
    diuretic = _rec(review, "furosemide")
    assert diuretic is not None
    assert any("sulfa" in flag.lower() for flag in diuretic["review_flags"])


# ---------------------------------------------------------------------------
# Conditions and history
# ---------------------------------------------------------------------------

def test_asthma_blocks_beta_blocker_for_review_rather_than_silently_offering_it():
    review = review_medications(
        symptoms=["chest pain"], conditions=["asthma"], age=55, risk_level="Medium"
    )
    assert _rec(review, "beta-blocker") is None
    blocked = _blocked(review, "beta-blocker")
    assert blocked is not None
    assert blocked["status"] == "review-before-use"
    assert "asthma" in " ".join(b["note"].lower() for b in blocked["blocks"])


def test_pregnancy_blocks_statin_and_ace_inhibitor():
    review = review_medications(
        conditions=["hypertension", "dyslipidaemia"], pregnancy=True, age=31, sex="female"
    )
    assert _blocked(review, "statin")["severity"] == "absolute"
    assert _blocked(review, "ramipril")["severity"] == "absolute"
    anticoagulant = _blocked(review, "anticoagulant")
    if anticoagulant is not None:
        assert anticoagulant["severity"] == "relative"


def test_prior_stroke_triggers_anticoagulation_consideration():
    review = review_medications(conditions=["TIA last year", "atrial fibrillation"], age=72)
    assert _rec(review, "anticoagulant") is not None


def test_condition_tags_detected_from_clinical_text():
    tags = detect_conditions("Known IHD, CABG in 2019, ex-smoker with high cholesterol")
    assert {"established_cad", "prior_pci_cabg", "smoking", "dyslipidemia"} <= set(tags)


# ---------------------------------------------------------------------------
# Labs
# ---------------------------------------------------------------------------

def test_egfr_26_contraindicates_metformin():
    review = review_medications(conditions=["diabetes"], labs={"egfr": 26}, age=68)
    metformin = _blocked(review, "metformin")
    assert metformin is not None
    assert metformin["status"] == "contraindicated"
    assert any(block["kind"] == "lab" for block in metformin["blocks"])


def test_hyperkalaemia_blocks_raas_blockade_and_mra():
    review = review_medications(
        conditions=["heart failure", "hypertension"], labs={"potassium": 6.1, "egfr": 55}, age=70
    )
    assert _blocked(review, "ramipril")["severity"] == "absolute"
    assert _blocked(review, "spironolactone")["severity"] == "absolute"


def test_lab_tags_thresholds_are_explicit():
    tags = lab_tags({"egfr": 28, "potassium": 5.2, "platelets": 90, "lvef": 32, "ldl": 190})
    assert tags["renal_severe"] == 28
    assert tags["borderline_hyperkalemia"] == 5.2
    assert tags["thrombocytopenia"] == 90
    assert tags["reduced_ef"] == 32
    assert tags["dyslipidemia_lab"] == 190


def test_missing_labs_are_reported_instead_of_assumed():
    review = review_medications(conditions=["diabetes", "chronic kidney disease"], age=60)
    joined = " ".join(review["missing_information"]).lower()
    assert "egfr" in joined
    # With eGFR supplied the renal gap is closed and no longer reported.
    with_labs = review_medications(conditions=["diabetes"], labs={"egfr": 70}, age=60, allergies=["none"], current_medications=["none recorded"])
    assert not any("eGFR/creatinine not supplied" in item for item in with_labs["missing_information"])


# ---------------------------------------------------------------------------
# Current medications & interactions
# ---------------------------------------------------------------------------

def test_current_medications_are_recognised_by_brand_name():
    keys = current_med_keys(["Disprin 75 mg", "Concor 5 mg", "Crestor 20 mg"])
    assert {"aspirin", "beta_blocker", "statin_high_intensity"} <= set(keys)


def test_aspirin_plus_documented_warfarin_flags_major_bleeding_interaction():
    review = review_medications(
        symptoms=["chest pain"],
        conditions=["atrial fibrillation"],
        current_medications=["warfarin"],
        age=70,
        risk_level="Medium",
    )
    pairs = [tuple(alert["pair"]) for alert in review["interaction_alerts"]]
    assert ("aspirin", "anticoagulant") in pairs
    alert = next(a for a in review["interaction_alerts"] if tuple(a["pair"]) == ("aspirin", "anticoagulant"))
    assert alert["severity"] == "major"
    assert "gastroprotection" in alert["action"]


def test_p2y12_plus_anticoagulant_is_flagged_major():
    review = review_medications(
        symptoms=["chest pain"],
        conditions=["atrial fibrillation"],
        current_medications=["warfarin"],
        age=70,
        risk_level="High",
    )
    pairs = [tuple(alert["pair"]) for alert in review["interaction_alerts"]]
    assert ("p2y12", "anticoagulant") in pairs


def test_nitrate_plus_pde5_inhibitor_is_a_major_interaction():
    review = review_medications(
        symptoms=["chest pain"], current_medications=["sildenafil"], age=58, risk_level="High"
    )
    pairs = [tuple(alert["pair"]) for alert in review["interaction_alerts"]]
    assert ("nitrate", "pde5_inhibitor") in pairs


def test_only_one_raas_strategy_is_offered():
    review = review_medications(
        conditions=["hypertension", "diabetes"], age=56, allergies=["none"], current_medications=["none recorded"]
    )
    ace = _rec(review, "ramipril")
    arb = _rec(review, "losartan")
    assert ace is not None and arb is not None
    assert arb["status"] == "alternative"
    assert "never combine" in arb["action"]
    pairs = [tuple(alert["pair"]) for alert in review["interaction_alerts"]]
    assert ("ace_inhibitor", "arb") not in pairs


def test_already_documented_drug_is_not_re_prescribed():
    review = review_medications(conditions=["hypertension"], current_medications=["amlodipine 5 mg"], age=54)
    ccb = _rec(review, "amlodipine")
    assert ccb["status"] == "already-documented"
    assert "verify dose" in ccb["action"]


# ---------------------------------------------------------------------------
# Orchestrator integration (the route path)
# ---------------------------------------------------------------------------

def test_orchestrator_review_bands_like_diagnose():
    result = run_medication_review(
        "crushing chest pain with sweating and pain in my left arm",
        patient={"age": 61, "sex": "male", "allergies": ["none"], "current_medications": ["none recorded"]},
    )
    assert result["diagnosis"]["risk_level"] == "High"
    assert result["medications"]["pathway"]["urgency"] == "emergency"
    assert "chest pain" in result["symptoms"]


def test_orchestrator_review_without_text_still_answers_from_patient_context():
    result = run_medication_review(
        "",
        patient={
            "age": 77,
            "conditions": ["chronic kidney disease"],
            "labs": {"egfr": 24, "potassium": 5.9},
            "allergies": ["none"],
            "current_medications": ["none recorded"],
        },
    )
    assert result["diagnosis"] is None
    review = result["medications"]
    assert _blocked(review, "spironolactone") is not None or _blocked(review, "ramipril") is not None
    assert review["patient_profile"]["labs_considered"]["renal_severe"] == 24


def test_every_review_carries_the_decision_support_disclaimer():
    review = review_medications(conditions=["hypertension"], age=50, allergies=["none"], current_medications=["none recorded"])
    assert "Decision support only" in review["disclaimer"]
    assert "Decision support only" in review["pathway"].get("statement", "") or review["pathway"]["statement"]


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
    print(f"\nAll {len(tests)} pharmacology cases passed.")


if __name__ == "__main__":
    main()
