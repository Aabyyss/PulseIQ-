"""Deterministic risk scores — direction, boundaries and what feeds them.

Every case asserts a clinical direction or an exact published value: the band a
total falls in, the point a boundary value earns, the mortality a printed
nomogram row gives, and the fact that an unknown input leaves the score
incomplete instead of scoring the patient as low risk. The wiring cases then
check that the medication and diagnosis layers read the scores rather than
hand-derived urgency. Runnable via pytest and directly
(``python backend/test_risk_scores.py``).
"""

import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.pharmacology_agent import review_medications  # noqa: E402
from agents.risk_scores_agent import cha2ds2_vasc, grace_score, heart_score  # noqa: E402
from backend import realtime_service  # noqa: E402
from backend.orchestrator import run_diagnosis_from_text, run_medication_review  # noqa: E402
from backend.risk_score_context import build_risk_scores  # noqa: E402


# ---------------------------------------------------------------------------
# HEART
# ---------------------------------------------------------------------------

def _heart(**overrides) -> dict:
    """A 50-year-old with a typical history, no ECG changes and a normal troponin."""
    base = dict(
        history="typical", ecg="normal", age=50,
        risk_factor_count=0, established_ascvd=False, troponin_ratio=0.5,
    )
    base.update(overrides)
    return heart_score(**base)


def test_heart_bands_follow_the_published_cutoffs():
    low = _heart(history="non_specific", ecg="normal", age=40)
    assert low["score"] == 0 and low["band"] == "low"
    intermediate = _heart(history="atypical", ecg="repolarisation", age=55, risk_factor_count=1)
    assert intermediate["score"] == 4 and intermediate["band"] == "intermediate"
    high = _heart(history="typical", ecg="st_deviation", age=70, risk_factor_count=3, troponin_ratio=5)
    assert high["score"] == 10 and high["band"] == "high"
    assert high["mace_risk_6_weeks"] == "50-65%"


def test_heart_age_and_risk_factor_bins():
    assert _heart(age=44)["components"]["age"]["points"] == 0
    assert _heart(age=45)["components"]["age"]["points"] == 1
    assert _heart(age=64)["components"]["age"]["points"] == 1
    assert _heart(age=65)["components"]["age"]["points"] == 2
    assert _heart(risk_factor_count=0)["components"]["risk_factors"]["points"] == 0
    assert _heart(risk_factor_count=2)["components"]["risk_factors"]["points"] == 1
    assert _heart(risk_factor_count=3)["components"]["risk_factors"]["points"] == 2
    # Established atherosclerotic disease scores 2 regardless of the count.
    established = _heart(risk_factor_count=0, established_ascvd=True)
    assert established["components"]["risk_factors"]["points"] == 2
    assert "atherosclerotic" in established["components"]["risk_factors"]["detail"]


def test_heart_troponin_scores_against_the_assay_ceiling():
    assert _heart(troponin_ratio=1.0)["components"]["troponin"]["points"] == 0
    assert _heart(troponin_ratio=1.5)["components"]["troponin"]["points"] == 1
    assert _heart(troponin_ratio=3.0)["components"]["troponin"]["points"] == 1
    assert _heart(troponin_ratio=3.1)["components"]["troponin"]["points"] == 2


def test_heart_without_a_troponin_is_incomplete_not_low_risk():
    score = _heart(history="typical", ecg="st_deviation", age=70, risk_factor_count=3, troponin_ratio=None)
    assert score["score"] is None
    assert score["band"] is None
    assert score["complete"] is False
    assert score["known_points"] == 8  # everything captured is still reported
    assert score["missing"] == ["troponin"]


# ---------------------------------------------------------------------------
# GRACE
# ---------------------------------------------------------------------------

def _grace(**overrides) -> dict:
    """The 'everything present' baseline every bin test then perturbs."""
    base = dict(
        age=68, heart_rate=100, systolic_bp=110, creatinine_mg_dl=1.0,
        killip="II", cardiac_arrest=False, st_deviation=True, elevated_markers=True,
    )
    base.update(overrides)
    return grace_score(**base)


def test_grace_bins_match_the_published_point_tables():
    assert _grace(age=29)["components"]["age"]["points"] == 0
    assert _grace(age=30)["components"]["age"]["points"] == 8
    assert _grace(age=89)["components"]["age"]["points"] == 91
    assert _grace(age=90)["components"]["age"]["points"] == 100
    assert _grace(heart_rate=49)["components"]["heart_rate"]["points"] == 0
    assert _grace(heart_rate=50)["components"]["heart_rate"]["points"] == 3
    assert _grace(heart_rate=200)["components"]["heart_rate"]["points"] == 46
    assert _grace(systolic_bp=79)["components"]["systolic_bp"]["points"] == 58
    assert _grace(systolic_bp=200)["components"]["systolic_bp"]["points"] == 0
    assert _grace(creatinine_mg_dl=0.4)["components"]["creatinine"]["points"] == 4
    assert _grace(creatinine_mg_dl=4.0)["components"]["creatinine"]["points"] == 28


def test_grace_flags_and_killip_are_scored_as_listed():
    baseline = _grace(killip="I", cardiac_arrest=False, st_deviation=False, elevated_markers=False)
    # Each flag adds exactly its published points on top of the same patient.
    assert _grace(killip="I", cardiac_arrest=True, st_deviation=False, elevated_markers=False)["score"] - baseline["score"] == 39
    assert _grace(killip="I", cardiac_arrest=False, st_deviation=True, elevated_markers=False)["score"] - baseline["score"] == 28
    assert _grace(killip="I", cardiac_arrest=False, st_deviation=False, elevated_markers=True)["score"] - baseline["score"] == 14
    assert _grace(killip="IV", cardiac_arrest=False, st_deviation=False, elevated_markers=False)["score"] - baseline["score"] == 59
    assert _grace(killip="IV")["components"]["killip"]["points"] == 59
    assert _grace(cardiac_arrest=True)["components"]["cardiac_arrest"]["points"] == 39
    assert _grace(st_deviation=True)["components"]["st_deviation"]["points"] == 28
    assert _grace(elevated_markers=True)["components"]["elevated_markers"]["points"] == 14
    assert _grace(killip="II")["components"]["killip"]["detail"] == "Killip class II"


def test_grace_bands_and_nomogram_mortality():
    assert _grace(age=29, heart_rate=40, systolic_bp=200, creatinine_mg_dl=0.3, killip="I",
                  cardiac_arrest=False, st_deviation=False, elevated_markers=False)["score"] == 1
    assert _grace()["band"] == "high"  # the baseline sums into the high band
    # A printed row is reported as printed, not interpolated.
    table_hit = _grace(age=29, heart_rate=40, systolic_bp=200, creatinine_mg_dl=0.3, killip="I",
                       cardiac_arrest=False, st_deviation=False, elevated_markers=False)
    assert table_hit["band"] == "low"
    assert table_hit["in_hospital_mortality"]["percent"] == 0.2  # score 1 <= first row
    assert table_hit["in_hospital_mortality"]["interpolated"] is False


def test_grace_mortality_interpolates_between_printed_rows_only_when_needed():
    from agents.risk_scores_agent import _grace_mortality_from_table

    assert _grace_mortality_from_table(140)["percent"] == 2.9
    assert _grace_mortality_from_table(140)["interpolated"] is False
    assert _grace_mortality_from_table(185)["percent"] == 11.4
    assert _grace_mortality_from_table(185)["interpolated"] is True
    assert _grace_mortality_from_table(400)["percent"] == 52.0


def test_grace_without_vitals_or_killip_is_incomplete():
    score = grace_score(age=68, heart_rate=None, systolic_bp=None, creatinine_mg_dl=None,
                        killip=None, cardiac_arrest=False, st_deviation=None, elevated_markers=True)
    assert score["score"] is None
    assert score["complete"] is False
    # Named, so the clinician can supply exactly what the score needs.
    for item in ("heart_rate", "systolic_bp", "creatinine", "Killip class", "st_deviation"):
        assert item in score["missing"]


# ---------------------------------------------------------------------------
# CHA₂DS₂-VASc
# ---------------------------------------------------------------------------

def test_cha2ds2_vasc_points_and_modifier():
    maxed = cha2ds2_vasc(age=80, sex="Female", heart_failure=True, hypertension=True,
                         diabetes=True, stroke_tia=True, vascular_disease=True)
    assert maxed["score"] == 9 and maxed["max_score"] == 9
    male = cha2ds2_vasc(age=80, sex="Male", heart_failure=True, hypertension=True,
                        diabetes=True, stroke_tia=True, vascular_disease=True)
    assert male["score"] == 8  # male sex adds nothing
    # The published adjusted-rate table is non-monotonic at the top: score 8
    # reads lower than score 7. Quoted as published, not smoothed.
    assert male["annual_stroke_risk_pct"] == 6.7
    assert cha2ds2_vasc(age=64, sex="Male")["annual_stroke_risk_pct"] == 0.0  # score 0
    seven = cha2ds2_vasc(age=80, sex="Male", heart_failure=True, hypertension=True,
                         diabetes=True, stroke_tia=True)
    assert seven["score"] == 7 and seven["annual_stroke_risk_pct"] == 9.6


def test_cha2ds2_vasc_age_bands_are_mutually_exclusive():
    assert cha2ds2_vasc(age=64, sex="Male")["components"]["age"]["points"] == 0
    assert cha2ds2_vasc(age=65, sex="Male")["components"]["age"]["points"] == 1
    assert cha2ds2_vasc(age=74, sex="Male")["components"]["age"]["points"] == 1
    assert cha2ds2_vasc(age=75, sex="Male")["components"]["age"]["points"] == 2
    # Prior stroke is worth two points on its own.
    stroke = cha2ds2_vasc(age=50, sex="Male", stroke_tia=True)
    assert stroke["components"]["stroke_tia"]["points"] == 2 and stroke["score"] == 2


def test_cha2ds2_vasc_anticoagulation_tiers_treat_sex_as_a_modifier():
    assert cha2ds2_vasc(age=40, sex="Male")["anticoagulation_tier"] == "none"
    assert cha2ds2_vasc(age=40, sex="Female")["anticoagulation_tier"] == "none"
    assert cha2ds2_vasc(age=40, sex="Male", hypertension=True)["anticoagulation_tier"] == "consider"
    assert cha2ds2_vasc(age=40, sex="Female", hypertension=True)["anticoagulation_tier"] == "consider"
    assert cha2ds2_vasc(age=40, sex="Male", hypertension=True, diabetes=True)["anticoagulation_tier"] == "recommended"
    assert cha2ds2_vasc(age=70, sex="Female")["anticoagulation_tier"] == "consider"
    assert cha2ds2_vasc(age=80, sex="Female")["anticoagulation_tier"] == "recommended"


def test_cha2ds2_vasc_without_sex_is_incomplete():
    score = cha2ds2_vasc(age=72, sex=None)
    assert score["score"] is None and score["complete"] is False
    assert score["missing"] == ["sex"]
    assert score["components"]["age"]["points"] == 1  # the rest is still reported


# ---------------------------------------------------------------------------
# What the encounter feeds the scores
# ---------------------------------------------------------------------------

def test_vitals_and_creatinine_come_from_the_clinical_text():
    scores = build_risk_scores(
        report_text="BP 90/60, HR 110, Killip class II. Creatinine 1.4 mg/dL. Troponin I: 0.06 ng/mL. ECG: ST depression.",
        patient={"age": "68", "sex": "Male"},
    )
    assert scores["inputs"]["vitals"] == {"heart_rate": 110, "systolic_bp": 90, "diastolic_bp": 60, "killip": "II"}
    assert scores["inputs"]["creatinine_mg_dl"] == 1.4
    assert scores["grace"]["complete"] is True


def test_creatinine_in_micromol_per_litre_is_converted_not_binned():
    scores = build_risk_scores(report_text="Creatinine 130 umol/L", patient={"age": "68", "sex": "Male"})
    # 130 / 88.4 = 1.471 mg/dL -> the 1.2-<1.6 bin (10 points), not the >4 bin.
    assert scores["inputs"]["creatinine_mg_dl"] == 1.471
    assert grace_score(
        age=68, heart_rate=None, systolic_bp=None, creatinine_mg_dl=scores["inputs"]["creatinine_mg_dl"],
        killip=None, cardiac_arrest=False, st_deviation=None, elevated_markers=None,
    )["components"]["creatinine"]["points"] == 10


def test_troponin_unit_forms_and_a_qualitative_positive():
    high_sensitivity = build_risk_scores(report_text="hs-TnI 90 ng/L", patient={"age": "68", "sex": "Male"})
    assert high_sensitivity["inputs"]["troponin"]["ratio"] == 2.25  # 0.09 ng/mL vs the 0.04 ceiling
    assert high_sensitivity["inputs"]["elevated_markers"] is True

    qualitative = build_risk_scores(report_text="troponin positive", patient={"age": "68", "sex": "Male"})
    assert qualitative["heart"]["score"] is None  # no number, so the item cannot be scored
    assert "troponin" in qualitative["heart"]["missing"]
    assert qualitative["inputs"]["elevated_markers"] is True  # but GRACE's binary item can


def test_ecg_statements_map_onto_the_two_scores_that_need_them():
    def ecg(text: str) -> str | None:
        return build_risk_scores(report_text=text, patient={"age": "68", "sex": "Male"})["inputs"]["ecg"]

    assert ecg("ECG: ST elevation in II, III, aVF") == "st_deviation"
    assert ecg("ECG: ST depression in V4-V6") == "st_deviation"
    assert ecg("ECG: T wave inversion anteriorly") == "repolarisation"
    assert ecg("ECG: left ventricular hypertrophy") == "repolarisation"
    assert ecg("ECG: normal sinus rhythm, no acute changes") == "normal"
    assert ecg("no cardiac investigation documented") is None


def test_chest_pain_typicality_is_derived_and_explained():
    typical, _, _ = _history_reading_of(
        "crushing chest pain radiating to the left arm, he is sweating", ["chest pain"]
    )
    atypical, features, _ = _history_reading_of("chest pain radiating to the jaw", ["chest pain"])
    non_specific, none_features, _ = _history_reading_of("chest pain, no other detail", ["chest pain"])
    assert typical == "typical"
    assert atypical == "atypical" and features == ["radiation"]
    assert non_specific == "non_specific" and none_features == []

    scores = build_risk_scores(encounter_text="short of breath on exertion", patient={"age": "60", "sex": "Male"})
    assert scores["heart"]["score"] is None
    assert "history typicality" in scores["heart"]["missing"]  # HEART needs a chest-pain history


def test_established_ascvd_and_risk_factors_come_from_the_record_and_the_wording():
    recorded = build_risk_scores(
        patient={"age": "68", "sex": "Male", "conditions": ["prior MI", "diabetes", "hypertension"]}
    )
    assert "prior_mi" in recorded["inputs"]["established_ascvd"]
    assert recorded["heart"]["components"]["risk_factors"]["points"] == 2
    spoken = build_risk_scores(
        encounter_text="he has claudication and a family history of heart disease",
        patient={"age": "68", "sex": "Male"},
    )
    assert "peripheral_arterial_disease" in spoken["inputs"]["established_ascvd"]
    assert "family_history_cad" in spoken["inputs"]["heart_risk_factors"]


def test_stroke_risk_reports_whether_atrial_fibrillation_was_captured():
    without = build_risk_scores(encounter_text="chest pain", patient={"age": "80", "sex": "Male"})
    assert without["cha2ds2_vasc"]["applies_to"].startswith("atrial fibrillation (not captured")
    with_af = build_risk_scores(
        encounter_text="atrial fibrillation with rapid ventricular response",
        patient={"age": "80", "sex": "Male"},
    )
    assert with_af["inputs"]["atrial_fibrillation"] is True
    assert with_af["cha2ds2_vasc"]["score"] == 2 and with_af["cha2ds2_vasc"]["anticoagulation_tier"] == "recommended"


def test_the_same_encounter_always_produces_the_same_scores():
    kwargs = dict(
        encounter_text="crushing chest pain radiating to the left arm, sweaty, diabetic and hypertensive",
        report_text="BP 90/60, HR 110, Killip II, creatinine 1.4 mg/dL, troponin I 0.06 ng/mL, ECG: ST depression",
        patient={"age": "68", "sex": "Male", "conditions": ["hypertension"]},
        symptoms=["chest pain", "sweating"],
    )
    first, second = build_risk_scores(**kwargs), build_risk_scores(**kwargs)
    assert first == second


def _history_reading_of(narrative: str, symptoms: list[str]):
    from backend.risk_score_context import _history_reading

    return _history_reading(narrative, symptoms)


def _scored_encounter(**overrides) -> dict:
    """An ACS-shaped encounter whose scores are complete, unless overridden."""
    kwargs: dict = dict(
        encounter_text="crushing chest pain radiating to the left arm with sweating, and he is diabetic",
        report_text="BP 90/60, HR 110, Killip class II. Troponin I: 0.06 ng/mL. Creatinine 1.4 mg/dL. ECG: ST depression.",
        patient={"age": "68", "sex": "Male", "conditions": ["hypertension"]},
        symptoms=["chest pain", "sweating"],
    )
    kwargs.update(overrides)
    return build_risk_scores(**kwargs)


# ---------------------------------------------------------------------------
# The layers consume them
# ---------------------------------------------------------------------------

def test_the_medication_pathway_urgency_is_graded_by_the_scores():
    scores = _scored_encounter()
    assert scores["heart"]["band"] == "high"
    review = review_medications(
        symptoms=["chest pain"], conditions=["hypertension"], age=68, sex="Male", risk_scores=scores
    )
    assert review["pathway"]["urgency"] == "emergency"
    joined = " ".join(review["pathway"]["drivers"])
    assert "HEART" in joined and "GRACE" in joined
    assert any("HEART" in line for line in review["pathway"]["rationale"])
    assert review["risk_scores"]["heart"]["score"] == scores["heart"]["score"]


def test_an_intermediate_score_makes_the_encounter_urgent():
    """An ACS-equivalent presentation graded intermediate is urgent, not emergency.

    The chest pain itself is not captured here (dyspnoea is), so the presentation
    floor does not fire and the score is what decides.
    """
    scores = _scored_encounter(
        encounter_text="breathless climbing stairs since yesterday",
        report_text="BP 130/80, HR 80, Killip I, creatinine 1.0 mg/dL, troponin I: 0.06 ng/mL, ECG: T wave inversion",
        symptoms=["shortness of breath"],
    )
    assert scores["grace"]["band"] == "intermediate"
    review = review_medications(symptoms=["shortness of breath"], age=68, sex="Male", risk_scores=scores)
    assert review["pathway"]["urgency"] == "urgent"
    assert any("GRACE" in driver for driver in review["pathway"]["drivers"])


def test_a_score_can_never_soften_a_chest_pain_presentation():
    """The graded numbers are shown, but the ACS pathway stands (ADR-018)."""
    scores = _scored_encounter(
        encounter_text="chest pain since yesterday, no radiation",
        report_text="BP 130/80, HR 80, Killip I, creatinine 1.0 mg/dL, troponin I: 0.06 ng/mL, ECG: T wave inversion",
        symptoms=["chest pain"],
    )
    assert scores["heart"]["band"] == "intermediate"
    review = review_medications(symptoms=["chest pain"], age=68, sex="Male", risk_scores=scores)
    assert review["pathway"]["urgency"] == "emergency"
    assert any("HEART" in line for line in review["pathway"]["rationale"])
    assert review["pathway"]["drivers"][0] == "presentation"


def test_without_complete_scores_the_old_escalation_still_stands():
    review = review_medications(symptoms=["chest pain"], age=68, sex="Male")
    assert review["pathway"]["urgency"] == "emergency"  # ACS presentation, unchanged
    assert review["pathway"]["drivers"] == ["presentation"]


def test_atrial_fibrillation_gets_its_stroke_risk_graded_not_ordered():
    scores = build_risk_scores(
        encounter_text="atrial fibrillation with palpitations",
        patient={"age": "80", "sex": "Female", "conditions": ["hypertension", "diabetes"]},
    )
    review = review_medications(
        symptoms=["palpitations"], conditions=["atrial fibrillation", "hypertension", "diabetes"],
        age=80, sex="Female", risk_scores=scores,
    )
    graded = [item for item in review["indications"] if item["name"] == "atrial_fibrillation_stroke_risk"]
    assert graded and "CHA2DS2-VASc 5" in graded[0]["triggered_by"]
    assert "anticoagulation tier: recommended" in graded[0]["triggered_by"]

    below = build_risk_scores(
        encounter_text="atrial fibrillation", patient={"age": "50", "sex": "Male", "conditions": ["atrial fibrillation"]}
    )
    low = review_medications(
        symptoms=[], conditions=["atrial fibrillation"], age=50, sex="Male", risk_scores=below
    )
    flagged = [
        flag for rec in low["recommendations"] for flag in rec["review_flags"] if "CHA2DS2-VASc" in flag
    ]
    assert flagged, "a below-threshold score is stated on the anticoagulation option"


def test_a_stroke_risk_that_cannot_be_graded_is_reported_as_missing():
    scores = build_risk_scores(encounter_text="atrial fibrillation", patient={"age": "80", "conditions": ["atrial fibrillation"]}, symptoms=[])
    review = review_medications(symptoms=[], conditions=["atrial fibrillation"], age=80, risk_scores=scores)
    assert any("CHA2DS2-VASc incomplete" in item for item in review["missing_information"])


def test_the_diagnosis_layer_reports_the_scores_beside_the_model_band():
    diagnosis = run_diagnosis_from_text(
        "crushing chest pain",
        report_text="BP 90/60, HR 110, Killip II, creatinine 1.4 mg/dL, troponin I: 0.06 ng/mL, ECG: ST depression",
        patient={"age": "68", "sex": "Male"},
    )
    assert diagnosis["risk_level"] in ("Low", "Medium", "High")  # the model band stays
    assert diagnosis["risk_scores"]["grace"]["score"] is not None
    assert diagnosis["risk_scores"]["heart"]["band"] in ("low", "intermediate", "high")

    medication = run_medication_review(
        text="crushing chest pain radiating to the left arm",
        report_text="BP 90/60, HR 110, Killip II, creatinine 1.4 mg/dL, troponin I 0.06 ng/mL, ECG: ST depression",
        patient={"age": "68", "sex": "Male", "conditions": ["hypertension"]},
    )
    assert medication["risk_scores"]["heart"]["band"] == "high"
    assert medication["medications"]["pathway"]["urgency"] == "emergency"


def test_the_live_frame_carries_the_same_scores_the_review_used():
    original_translate = realtime_service.translate_to_english
    original_plan = realtime_service.generate_ai_copilot_plan
    realtime_service.translate_to_english = lambda text, language_hint="en-US": text
    realtime_service.generate_ai_copilot_plan = lambda **kwargs: {
        "doctor_questions": [], "recommended_tests": [], "next_steps": [],
        "diagnostic_impression": ["…"], "urgency": "high", "safety_note": "Decision support only.",
    }
    try:
        frame = realtime_service.process_live_transcript_entry(
            text="crushing chest pain radiating to the left arm, sweating",
            speaker="patient",
            report_text="BP 90/60, HR 110, Killip II, troponin I 0.06 ng/mL, creatinine 1.4 mg/dL, ECG: ST depression",
            patient={"age": "68", "sex": "Male", "conditions": ["hypertension"], "allergies": ["none"]},
        )
    finally:
        realtime_service.translate_to_english = original_translate
        realtime_service.generate_ai_copilot_plan = original_plan

    assert frame["risk_scores"]["heart"]["band"] == "high"
    assert frame["diagnosis"]["risk_scores"] == frame["risk_scores"]  # one computation, one answer
    assert frame["medication_review"]["risk_scores"]["heart"]["score"] == frame["risk_scores"]["heart"]["score"]
    assert frame["medication_review"]["pathway"]["urgency"] == "emergency"


def test_a_comma_written_report_reaches_the_equation_unchanged():
    """The decimal comma and the micro sign are parser details, not score inputs.

    The same patient and the same lipids, written the way a European report
    prints them ("5,5 mmol/L", "130 µmol/L"), must reach the equation with the
    same numbers as the dot-and-ASCII version — the parser resolves the spelling
    before the scores ever see a value.
    """
    dotted = build_risk_scores(
        encounter_text="white male, never smoked, not diabetic, 68 years",
        report_text="BP 150/90. Total cholesterol 5.5 mmol/L, HDL 1.3 mmol/L, creatinine 130 umol/L.",
        patient={"age": "68", "sex": "Male", "race": "white"},
    )
    comma = build_risk_scores(
        encounter_text="white male, never smoked, not diabetic, 68 years",
        report_text="BP 150/90. Total cholesterol 5,5 mmol/L. HDL 1,3 mmol/L. Creatinine 130 µmol/L.",
        patient={"age": "68", "sex": "Male", "race": "white"},
    )
    assert comma["inputs"]["total_cholesterol_mg_dl"] == 212.7
    assert comma["inputs"]["hdl_mg_dl"] == 50.3
    assert comma["inputs"]["creatinine_mg_dl"] == 1.471
    assert comma["inputs"] == dotted["inputs"]
    assert comma["ascvd"]["risk_pct"] == dotted["ascvd"]["risk_pct"]
    assert comma["ascvd"]["category"] == dotted["ascvd"]["category"]


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
    print(f"\nAll {len(tests)} risk-score cases passed.")


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# ASCVD (2013 ACC/AHA Pooled Cohort Equations)
# ---------------------------------------------------------------------------

# The guideline's own worked example: 55 years, total cholesterol 213 mg/dL,
# HDL 50 mg/dL, systolic BP 120 mmHg untreated, non-smoker, non-diabetic.
_PCE_EXAMPLE = dict(
    age=55, total_cholesterol_mg_dl=213, hdl_mg_dl=50, systolic_bp=120,
    treated_for_hypertension=False, current_smoker=False, diabetes=False,
)


def test_the_pooled_cohort_example_matches_the_published_reference_values():
    from agents.risk_scores_agent import ascvd_score

    # Printed to one decimal, the guideline's example reads 2.1 / 3.0 / 5.3 / 6.1.
    # White men come out at 5.4 here (5.3786): the reference implementation of the
    # same coefficients reports 5.378606% and notes that its rounded coefficient
    # table need not reproduce the guideline's printed 5.3 exactly.
    expected = {
        ("white", "female"): 2.1,
        ("african_american", "female"): 3.0,
        ("white", "male"): 5.4,
        ("african_american", "male"): 6.1,
    }
    for (race, sex), want in expected.items():
        got = ascvd_score(race=race, sex=sex, **_PCE_EXAMPLE)["risk_pct"]
        assert got == want, f"{race} {sex}: {got} != {want}"


def test_the_unrounded_risk_matches_the_reference_implementation():
    from agents.risk_scores_agent import _ascvd_risk, _ascvd_term_values

    values = _ascvd_term_values(
        age=55, total_cholesterol_mg_dl=213, hdl_mg_dl=50, systolic_bp=120,
        treated_for_hypertension=False, current_smoker=False, diabetes=False,
    )
    assert round(_ascvd_risk("aa_men", values), 4) == 6.0611
    assert round(_ascvd_risk("white_men", values), 4) == 5.3786


def test_an_unknown_input_leaves_the_equation_unscored_and_named():
    from agents.risk_scores_agent import ascvd_score

    incomplete = {**_PCE_EXAMPLE, "hdl_mg_dl": None}
    scored = ascvd_score(race="white", sex="male", **incomplete)
    assert scored["score"] is None and scored["complete"] is False
    assert scored["missing"] == ["HDL cholesterol"]
    assert "HDL cholesterol" in scored["note"]

    # An unheard smoking/diabetes status is unknown, not "no".
    unknown = ascvd_score(race="white", sex="male", **{**_PCE_EXAMPLE, "current_smoker": None})
    assert unknown["score"] is None and "smoking status" in unknown["missing"]


def test_race_not_captured_reports_the_higher_sex_matched_equation():
    from agents.risk_scores_agent import ascvd_score

    both = ascvd_score(race=None, sex="male", **_PCE_EXAMPLE)
    assert both["risk_pct"] == 6.1 and both["group"] == "African American men"
    assert both["race_captured"] is False
    assert both["alternative"] == {"group": "white men", "risk_pct": 5.4}
    assert "Race/ethnicity was not captured" in both["note"]


def test_inputs_outside_the_derived_range_are_flagged_not_hidden():
    from agents.risk_scores_agent import ascvd_score

    young = ascvd_score(race="white", sex="male", **{**_PCE_EXAMPLE, "age": 35})
    assert young["risk_pct"] is not None  # still computed ...
    assert young["in_range"] is False  # ... but not presented as validated
    assert "age 35" in young["out_of_range"][0]


def test_every_term_of_the_sum_is_reported_with_its_coefficient():
    from agents.risk_scores_agent import ascvd_score

    scored = ascvd_score(race="white", sex="male", **_PCE_EXAMPLE)
    terms = scored["components"]
    assert terms["ln(age)"]["coefficient"] == 12.344
    # The reported contributions are rounded to 4 decimals, so they add up to the
    # reported sum only to that precision.
    assert abs(sum(term["contribution"] for term in terms.values()) - scored["linear_predictor"]["sum"]) < 0.001
    assert scored["category"] == "borderline"
    assert scored["statin_indicated"] is False  # 5.4% is below the 7.5% threshold
    higher = ascvd_score(
        race="white", sex="male",
        **{**_PCE_EXAMPLE, "age": 68, "systolic_bp": 150, "current_smoker": True},
    )
    assert higher["category"] == "high" and higher["statin_indicated"] is True


def test_the_encounter_assembles_the_equation_from_the_record_and_the_wording():
    scores = build_risk_scores(
        encounter_text="chest pain, white male, never smoked, not diabetic",
        report_text="BP 120/80. Total cholesterol 213 mg/dL, HDL 50 mg/dL.",
        patient={"age": "55", "sex": "Male"},
    )
    assert scores["ascvd"]["complete"] is True
    assert scores["ascvd"]["risk_pct"] == 5.4
    assert scores["ascvd"]["group"] == "white men"
    assert scores["inputs"]["current_smoker"] is False
    assert scores["inputs"]["diabetes_status"] is False

    # mmol/L is converted, never read as if it were mg/dL. (Known gap: the
    # lab-report parser mis-attributes the unit of an HDL value written in
    # mmol/L when the phrasing puts it after a comma, so this covers the
    # cholesterol conversion it does report; the equation consumes the unit the
    # parser reports rather than assuming mg/dL.)
    converted = build_risk_scores(
        encounter_text="white male, never smoked, not diabetic",
        report_text="BP 120/80. Total cholesterol 5.5 mmol/L, HDL 50 mg/dL.",
        patient={"age": "55", "sex": "Male"},
    )
    assert converted["inputs"]["total_cholesterol_mg_dl"] == 212.7
    assert converted["inputs"]["hdl_mg_dl"] == 50.0


def test_a_recorded_antihypertensive_selects_the_treated_blood_pressure_term():
    scores = build_risk_scores(
        encounter_text="white male, never smoked, not diabetic",
        report_text="BP 120/80. Total cholesterol 213 mg/dL, HDL 50 mg/dL.",
        patient={"age": "55", "sex": "Male", "current_medications": ["amlodipine"]},
    )
    assert scores["inputs"]["bp_treated"] is True
    assert "ln(systolic BP), treated" in scores["ascvd"]["components"]
    assert "ln(systolic BP), untreated" not in scores["ascvd"]["components"]


def test_an_incomplete_equation_is_named_in_the_encounter_gaps():
    scores = build_risk_scores(encounter_text="chest pain", patient={"age": "68", "sex": "Male"})
    gaps = " | ".join(scores["missing"])
    assert "ASCVD-PCE: total cholesterol" in gaps
    assert "ASCVD-PCE: HDL cholesterol" in gaps


def test_the_diagnosis_and_medication_paths_carry_the_equation():
    diagnosis = run_diagnosis_from_text(
        "crushing chest pain, white male, never smoked, not diabetic",
        report_text="BP 120/80. Total cholesterol 213 mg/dL, HDL 50 mg/dL, creatinine 1.0 mg/dL, HR 80, Killip I",
        patient={"age": "55", "sex": "Male"},
    )
    assert diagnosis["risk_scores"]["ascvd"]["risk_pct"] is not None

    medication = run_medication_review(
        text="crushing chest pain, white male, never smoked, not diabetic",
        report_text="BP 120/80. Total cholesterol 213 mg/dL, HDL 50 mg/dL, creatinine 1.0 mg/dL, HR 80, Killip I",
        patient={"age": "55", "sex": "Male"},
    )
    assert medication["risk_scores"]["ascvd"]["category"] in ("low", "borderline", "intermediate", "high")


def _ascvd_encounter(**overrides):
    kwargs = dict(
        encounter_text="white male, never smoked, not diabetic",
        report_text="BP 120/80. Total cholesterol 213 mg/dL, HDL 50 mg/dL, creatinine 1.0 mg/dL.",
        patient={"age": "55", "sex": "Male"},
    )
    kwargs.update(overrides)
    return build_risk_scores(**kwargs)


def test_the_primary_prevention_statin_is_graded_by_the_equation():
    scores = _ascvd_encounter(
        encounter_text="white male, never smoked, not diabetic",
        report_text="BP 150/90. Total cholesterol 213 mg/dL, HDL 50 mg/dL, creatinine 1.0 mg/dL.",
        patient={"age": "68", "sex": "Male"},
    )
    assert scores["ascvd"]["category"] == "high"

    review = review_medications(age=68, sex="Male", risk_scores=scores)
    statins = [rec for rec in review["recommendations"] if rec["drug_class"] == "statin"]
    assert statins, "the equation's threshold is what offers the primary-prevention statin"
    assert any("ASCVD 10-year risk" in reason for rec in statins for reason in rec["triggered_by"])

    # A ten-year probability is a chronic risk: it must never escalate an encounter.
    assert review["pathway"]["urgency"] == "routine"
    assert "ascvd" not in " ".join(review["pathway"]["drivers"]).lower()


def test_a_below_threshold_equation_says_why_a_statin_is_not_automatic():
    scores = _ascvd_encounter()
    assert scores["ascvd"]["risk_pct"] == 5.4

    review = review_medications(conditions=["dyslipidemia"], age=55, sex="Male", risk_scores=scores)
    offered = {rec["drug"] for rec in review["recommendations"]}
    assert "Moderate-intensity statin (primary prevention)" not in offered
    flags = [
        flag for rec in review["recommendations"] if rec["drug_class"] == "statin"
        for flag in rec["review_flags"]
    ]
    assert any("below the 7.5% threshold" in flag for flag in flags)


def test_an_ungradable_equation_is_named_when_a_laboratory_panel_arrived():
    scores = _ascvd_encounter(
        report_text="Creatinine 1.0 mg/dL.",
        encounter_text="white male, never smoked, not diabetic",
    )
    assert scores["ascvd"]["complete"] is False
    review = review_medications(labs={"creatinine": 1.0}, age=55, sex="Male", risk_scores=scores)
    assert any("ASCVD 10-year risk incomplete" in item for item in review["missing_information"])


def test_a_recorded_race_selects_the_model_group_whatever_its_format():
    for recorded in ("african_american", "African-American", "African American", "Black"):
        scores = _ascvd_encounter(
            encounter_text="chest discomfort, never smoked, not diabetic",
            report_text="BP 150/90. Total cholesterol 213 mg/dL, HDL 50 mg/dL.",
            patient={"age": "68", "sex": "Male", "race": recorded},
        )
        assert scores["ascvd"]["group"] == "African American men", recorded
        assert scores["ascvd"]["race_captured"] is True
        assert scores["ascvd"]["alternative"] is None

    # With no race recorded the higher of the two sex-matched models is shown,
    # which here is the white-men equation rather than an assumption about race.
    unstated = _ascvd_encounter(
        encounter_text="chest discomfort, never smoked, not diabetic",
        report_text="BP 150/90. Total cholesterol 213 mg/dL, HDL 50 mg/dL.",
        patient={"age": "68", "sex": "Male"},
    )
    assert unstated["ascvd"]["group"] == "white men"
    assert unstated["ascvd"]["alternative"] == {"group": "African American men", "risk_pct": 14.6}
    assert unstated["ascvd"]["risk_pct"] > unstated["ascvd"]["alternative"]["risk_pct"]
