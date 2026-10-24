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


def test_the_allergy_clause_ends_where_the_next_statement_starts():
    """A drug named after the allergy must not itself become an allergy."""
    mentions = extract_allergy_mentions("allergic to aspirin and I take warfarin 5 mg daily")
    joined = " ".join(mentions).lower()
    assert "aspirin" in joined
    assert "warfarin" not in joined

    spoken = extract_allergy_mentions(
        "she is allergic to penicillin but takes amoxicillin for her chest"
    )
    assert [term.lower() for term in spoken] == ["penicillin"]

    # …while a genuine substance list still yields both substances.
    both = extract_allergy_mentions("allergic to aspirin and sulfa drugs")
    assert "aspirin" in " ".join(both).lower()
    assert "sulfa" in " ".join(both).lower()


def test_a_following_clause_is_not_read_as_an_allergy():
    """The words after the allergy belong to the next statement, not to the list."""
    for spoken, expected in (
        ("he is allergic to Aspirin and is a known hypertensive", ["aspirin"]),
        ("allergic to penicillin and was started on amoxicillin yesterday", ["penicillin"]),
        ("she is allergic to sulfa and has asthma", ["sulfa"]),
        ("allergic to iodine and takes metformin", ["iodine"]),
    ):
        mentions = [term.lower() for term in extract_allergy_mentions(spoken)]
        assert mentions == expected, spoken
    # A substance list with no verb is still a list.
    two = [term.lower() for term in extract_allergy_mentions("allergic to aspirin and sulfa")]
    assert two == ["aspirin", "sulfa"]


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


def test_a_mmol_ldl_still_reaches_the_dyslipidaemia_indication():
    """The lipid gate reads a flattened lab map: the unit must be applied first.

    "LDL 4.2 mmol/L" is 162 mg/dL and belongs above the 160 mg/dL threshold, but
    read as a bare 4.2 it never fired the indication that offers a statin.
    """
    from backend.lab_report import labs_for_review

    labs = labs_for_review("LDL 4.2 mmol/L")
    assert labs["ldl"] == 162.414
    assert lab_tags(labs)["dyslipidemia_lab"] == 162.414
    assert "dyslipidemia_lab" not in lab_tags(labs_for_review("LDL 100 mg/dL"))


def test_the_lipid_gate_acts_at_the_high_band_for_either_fraction():
    """The reference-range boundary is not the treatment threshold.

    The screening flags LDL above 130 mg/dL and non-HDL above 160 (the
    borderline-high boundaries), while the option is offered at the *high*
    boundaries — 160 and 190, the same 30 mg/dL apart — so neither fraction is
    held to the other's number, and a panel that is merely flagged offers nothing
    automatically.
    """
    from backend.lab_report import labs_for_review, screen_report_text

    borderline = screen_report_text("LDL 140 mg/dL. non-HDL 170 mg/dL.")
    assert {v["key"] for v in borderline["values"] if v["severity"] == "abnormal"} == {"ldl", "non_hdl"}
    assert lab_tags(labs_for_review("LDL 140 mg/dL. non-HDL 170 mg/dL.")) == {}
    assert lab_tags({"ldl": 160.0, "non_hdl": 190.0}) == {"dyslipidemia_lab": 160.0, "non_hdl_high": 190.0}


def test_both_fractions_above_threshold_give_two_reasons_one_option():
    """Two reasons for one decision, in the order the guideline reads them.

    LDL is the primary target and is named first; the non-HDL reason is added
    rather than replacing it, and the same statin is offered once.
    """
    review = review_medications(symptoms=["chest pain"], labs={"ldl": 165.0, "non_hdl": 200.0})
    statins = [rec for rec in review["recommendations"] if rec["drug_class"] == "statin"]
    assert len(statins) == 1
    assert statins[0]["indications"] == ["suspected_acs", "dyslipidemia_lab", "non_hdl_high"]
    assert statins[0]["triggered_by"] == [
        "chest pain reported (suspected acute coronary syndrome)",
        "LDL 165 mg/dL",
        "non-HDL 200 mg/dL",
    ]


def test_a_panel_that_prints_only_non_hdl_still_raises_the_statin():
    """The fraction the lipid decision turns on is not always the one printed.

    A report written in non-HDL terms — and a panel whose non-HDL is derived from
    a printed total and HDL — reached the review as a number no gate read, so no
    lipid-lowering option was offered at all. The gate reads the fraction's own
    threshold (190 mg/dL, LDL-C's 160 shifted by the convention's 30 mg/dL) and
    names it as the reason, rather than attributing an LDL figure to the panel.
    """
    from backend.lab_report import labs_for_review

    printed = labs_for_review("non-HDL 5.0 mmol/L")
    assert printed["non_hdl"] == 193.35
    assert lab_tags(printed)["non_hdl_high"] == 193.35

    derived = labs_for_review("Total cholesterol 220 mg/dL, HDL 30 mg/dL.")  # non-HDL 190, not printed
    assert lab_tags(derived)["non_hdl_high"] == 190.0

    review = review_medications(symptoms=["chest pain"], labs=printed)
    statin = next(rec for rec in review["recommendations"] if rec["drug_class"] == "statin")
    assert "non_hdl_high" in statin["indications"]
    assert "non-HDL 193.35 mg/dL" in statin["triggered_by"]
    assert any(
        item["name"] == "non_hdl_high" and "non-HDL 193.35 mg/dL" == item["triggered_by"]
        for item in review["indications"]
    )
    # Below the fraction's own threshold nothing is offered for it, and LDL's
    # threshold is not quietly applied to a number that is not an LDL.
    assert "non_hdl_high" not in lab_tags({"non_hdl": 189.0})
    assert "non_hdl_high" not in lab_tags({"non_hdl": 0.0})


# ---------------------------------------------------------------------------
# Catalogue invariants — the tables a clinician is asked to trust
# ---------------------------------------------------------------------------

def test_every_drug_and_rule_names_a_source_that_resolves():
    """A citation nobody can follow is the same as no citation.

    Every entry carries at least one id from SOURCES, and every id resolves to a
    title and a publisher URL. This is the check that keeps a new drug from
    arriving with prose evidence and no source, and a new rule from arriving with
    no source at all.
    """
    from agents import pharmacology_agent as pharmacology

    assert len(pharmacology.SOURCES) >= 10
    for source_id, source in pharmacology.SOURCES.items():
        assert source.get("title"), source_id
        assert str(source.get("url", "")).startswith("http"), source_id

    for drug in pharmacology.DRUGS:
        ids = drug.get("source")
        assert ids, f"{drug['key']} has no source"
        for source_id in ids if isinstance(ids, list) else [ids]:
            assert source_id in pharmacology.SOURCES, f"{drug['key']} -> {source_id}"

    for rule in pharmacology.INTERACTIONS:
        ids = rule.get("source")
        assert ids, f"{rule['a']} + {rule['b']} has no source"
        for source_id in ids if isinstance(ids, list) else [ids]:
            assert source_id in pharmacology.SOURCES, f"{rule['a']} + {rule['b']} -> {source_id}"


def test_the_catalogue_has_no_duplicate_key_name_or_rule_pair():
    from agents import pharmacology_agent as pharmacology

    keys = [drug["key"] for drug in pharmacology.DRUGS]
    names = [drug["name"] for drug in pharmacology.DRUGS]
    assert len(keys) == len(set(keys))
    assert len(names) == len(set(names))
    pairs = [tuple(sorted((rule["a"], rule["b"]))) for rule in pharmacology.INTERACTIONS]
    assert len(pairs) == len(set(pairs))
    for rule in pharmacology.INTERACTIONS:
        assert rule["a"] != rule["b"], rule
        assert rule["severity"] in {"major", "moderate"}, rule


def test_every_rule_target_is_a_drug_a_class_or_an_alias():
    """A rule aimed at a key nothing produces is a rule that can never fire."""
    from agents import pharmacology_agent as pharmacology

    known = (
        {drug["key"] for drug in pharmacology.DRUGS}
        | {drug["drug_class"] for drug in pharmacology.DRUGS}
        | set(pharmacology.MED_ALIASES)
    )
    for rule in pharmacology.INTERACTIONS:
        assert rule["a"] in known, rule
        assert rule["b"] in known, rule


def test_every_option_can_be_recognised_as_a_current_medication():
    """A drug that cannot be matched in the current list cannot be screened.

    One entry per class is enough — the two statin entries describe the same
    molecules, so the alias table names the class once.
    """
    from agents import pharmacology_agent as pharmacology

    aliased_classes = {
        drug["drug_class"]
        for drug in pharmacology.DRUGS
        if drug["key"] in pharmacology.MED_ALIASES
    }
    for drug in pharmacology.DRUGS:
        assert drug["key"] in pharmacology.MED_ALIASES or drug["drug_class"] in aliased_classes, drug["key"]


def test_every_option_states_a_dose_a_monitoring_plan_and_its_evidence():
    from agents import pharmacology_agent as pharmacology

    for drug in pharmacology.DRUGS:
        for field in ("indications", "allergens", "monitoring", "dose_note", "evidence", "source"):
            assert drug.get(field), f"{drug['key']} has no {field}"
        assert drug["priority"] >= 1
