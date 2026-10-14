"""Reference-range report screening (Area 5 of the improvement review).

Covers: numeric parsing, unit-aware ranges, critical-first ordering,
explainability (matched text + reference band on every flag), and
text-only ECG findings.
"""

from backend.lab_report import screen_report_text


CRITICAL_REPORT = """
Lipid profile: Total cholesterol 248 mg/dL, LDL 168 mg/dL, HDL 34 mg/dL,
triglycerides 210 mg/dL. Potassium 6.4 mmol/L. Sodium 138 mmol/L.
Creatinine 1.1 mg/dL. HbA1c 7.2 %.
Echo: LVEF 35%.
ECG: anterior ST elevation, T wave inversion in V4-V6.
"""


def test_parses_numeric_values_with_units():
    result = screen_report_text(CRITICAL_REPORT)
    keys = {v["key"] for v in result["values"]}
    assert {"troponin_i", "ldl", "hdl", "total_cholesterol", "triglycerides",
            "potassium", "sodium", "creatinine", "hba1c", "lvef"} <= keys or {
        "ldl", "hdl", "total_cholesterol", "triglycerides",
        "potassium", "sodium", "creatinine", "hba1c", "lvef"} <= keys
    values = {v["key"]: v for v in result["values"]}
    assert values["potassium"]["value"] == 6.4
    assert values["ldl"]["value"] == 168
    assert values["lvef"]["value"] == 35
    assert values["hba1c"]["unit"] == "%"


def test_flags_abnormal_values_against_reference_ranges():
    result = screen_report_text(CRITICAL_REPORT)
    values = {v["key"]: v for v in result["values"]}
    # Potassium 6.4 crosses the 6.0 critical ceiling.
    assert values["potassium"]["status"] == "critical_high"
    assert values["potassium"]["severity"] == "critical"
    # LDL 168 is high but not critical.
    assert values["ldl"]["status"] == "high"
    assert values["ldl"]["severity"] == "abnormal"
    # Sodium 138 is normal.
    assert values["sodium"]["status"] == "normal"
    # EF 35% is below the 55% floor.
    assert values["lvef"]["status"] == "low"


def test_criticals_sort_first():
    result = screen_report_text(CRITICAL_REPORT)
    severities = [v["severity"] for v in result["values"]]
    rank = {"critical": 0, "abnormal": 1, "normal": 2}
    assert severities == sorted(severities, key=lambda s: rank[s])


def test_every_flag_carries_matched_text_reference_and_explanation():
    result = screen_report_text(CRITICAL_REPORT)
    for value in result["values"]:
        if value["severity"] == "normal":
            continue
        assert value["matched_text"], f"missing matched_text for {value['key']}"
        assert value["reference"], f"missing reference for {value['key']}"
        assert value["explanation"], f"missing explanation for {value['key']}"


def test_text_only_ecg_findings_are_flagged():
    result = screen_report_text(CRITICAL_REPORT)
    flag_names = [f["name"] for f in result["text_flags"]]
    assert any("ST elevation" in name for name in flag_names)
    st = next(f for f in result["text_flags"] if "ST elevation" in f["name"])
    assert st["severity"] == "critical"
    assert st["explanation"]


def test_summary_counts_and_message():
    result = screen_report_text(CRITICAL_REPORT)
    summary = result["summary"]
    assert summary["parsed"] is True
    assert summary["critical"] >= 2  # potassium + ST elevation
    assert summary["abnormal"] >= 3  # LDL, HDL low, TG, EF, T-wave...
    assert "critical" in result["message"].lower()


def test_normal_report_reports_clean():
    result = screen_report_text(
        "Sodium 140 mmol/L. Potassium 4.1 mmol/L. Creatinine 0.9 mg/dL."
    )
    assert result["summary"]["critical"] == 0
    assert result["summary"]["abnormal"] == 0
    assert result["summary"]["normal"] == 3
    assert "within" in result["message"].lower()


def test_empty_input_is_not_an_error():
    result = screen_report_text("")
    assert result["summary"]["parsed"] is False
    assert result["values"] == []


def test_unrecognised_text_explains_how_to_fix():
    result = screen_report_text("Patient feels unwell today.")
    assert result["summary"]["parsed"] is False
    assert "Troponin" in result["message"]


def test_qualitative_troponin_positive_flags_without_number():
    result = screen_report_text("High-sensitivity troponin positive. ECG unremarkable.")
    names = [f["name"] for f in result["text_flags"]]
    assert any("Troponin" in n for n in names)
    # Numeric troponin present → no duplicate qualitative flag.
    result2 = screen_report_text("Troponin I: 0.02 ng/mL")
    assert not any("positive" in f["name"].lower() for f in result2["text_flags"])


def test_unit_aware_ranges_mmol_vs_mgdl():
    # Cholesterol in mmol/L must use the mmol/L band (5.2), not 200.
    result = screen_report_text("Total cholesterol 6.1 mmol/L")
    value = result["values"][0]
    assert value["status"] == "high"
    assert "5.2" in value["reference"]


def test_gt_lt_bounds_respected():
    result = screen_report_text("Troponin I <0.01 ng/mL")
    value = next(v for v in result["values"] if v["key"] == "troponin_i")
    assert value["status"] == "normal"


def test_prose_values_read_aloud_are_parsed_like_a_printed_line():
    """"his eGFR is 26" and "a creatinine of 1.2" are values, not prose noise."""
    result = screen_report_text(
        "His potassium is 6.1 mmol/L, his eGFR is 26 and a creatinine of 1.2 mg/dL."
    )
    values = {v["key"]: v for v in result["values"]}
    assert values["potassium"]["value"] == 6.1
    assert values["potassium"]["status"] == "critical_high"
    assert values["egfr"]["value"] == 26
    assert values["creatinine"]["value"] == 1.2


def test_a_bare_number_with_no_value_marker_is_still_ignored():
    """The incidental-number guard survives: no unit, no colon, no copula."""
    assert screen_report_text("cholesterol 40").get("values") == []


# ---------------------------------------------------------------------------
# Unit attribution
# ---------------------------------------------------------------------------

def test_a_sentence_final_unit_is_not_part_of_the_unit():
    """A trailing period must not swallow the unit token that precedes it.

    "Total cholesterol 5.5 mmol/L." used to read "mmol/l." as the unit, miss the
    lookup table and fall back to mg/dL — grading a 5.5 mmol/L result against the
    200 mg/dL band, where it looked normal.
    """
    result = screen_report_text("Total cholesterol: 5.5 mmol/L.")
    value = next(v for v in result["values"] if v["key"] == "total_cholesterol")
    assert value["unit"] == "mmol/l"
    assert value["status"] == "high"
    assert "5.2" in value["reference"]


def test_a_lipid_value_keeps_its_unit_whatever_punctuation_follows_it():
    cases = [
        ("Total cholesterol 5.5 mmol/L, HDL 1.3 mmol/L.",
         {"total_cholesterol": "mmol/l", "hdl": "mmol/l"}),
        ("Total cholesterol: 5.5 mmol/L. HDL: 1.3 mmol/L.",
         {"total_cholesterol": "mmol/l", "hdl": "mmol/l"}),
        ("Cholesterol 5.5 mmol/L. HDL 50 mg/dL.",
         {"total_cholesterol": "mmol/l", "hdl": "mg/dl"}),
        ("HDL 1.3 mmol/L.",
         {"hdl": "mmol/l"}),
        ("LDL 3.4 mmol/L, HDL 1.0 mmol/L, triglycerides 2.1 mmol/L.",
         {"ldl": "mmol/l", "hdl": "mmol/l", "triglycerides": "mmol/l"}),
        ("Total cholesterol 5.5 mmol/L (fasting), HDL 1.3 mmol/L (repeat)",
         {"total_cholesterol": "mmol/l", "hdl": "mmol/l"}),
        ("LDL: 3.4 mmol/L. Triglycerides: 2.1 mmol/L.",
         {"ldl": "mmol/l", "triglycerides": "mmol/l"}),
        ("HDL 1.3 mmol / L",
         {"hdl": "mmol/l"}),
        ("HDL 1.3mmol/L",
         {"hdl": "mmol/l"}),
        ("Total cholesterol 213 mg/dL, HDL 50 mg/dL.",
         {"total_cholesterol": "mg/dl", "hdl": "mg/dl"}),
    ]
    for text, expected in cases:
        units = {v["key"]: v["unit"] for v in screen_report_text(text)["values"]}
        for key, unit in expected.items():
            assert units.get(key) == unit, f"{text!r} -> {key} read as {units.get(key)!r}"


def test_an_mmol_lipid_is_not_flagged_against_the_mgdl_band():
    """The bug had a clinical consequence, so the fix is asserted clinically.

    HDL 1.3 mmol/L is 50 mg/dL: within range. Judged against the mg/dL floor of
    40 it was reported as below reference, and the same misattribution made a
    cholesterol of 5.5 mmol/L look normal.
    """
    result = screen_report_text("HDL 1.3 mmol/L. Total cholesterol 5.5 mmol/L.")
    values = {v["key"]: v for v in result["values"]}
    assert values["hdl"]["status"] == "normal"
    assert values["hdl"]["reference"] == "≥1.0 mmol/l"
    assert values["total_cholesterol"]["status"] == "high"
    # The two printed values also define non-HDL (212.7 - 50.3 = 162.4 mg/dL),
    # which is over its own 160 mg/dL band — so the count is two abnormal values
    # now. Neither of them is the HDL, which is what this case is about.
    assert (values["non_hdl"]["computed"], values["non_hdl"]["status"]) == (True, "high")
    assert result["summary"]["abnormal"] == 2


def test_the_unit_normaliser_ignores_punctuation_and_spacing():
    from backend.lab_report import _normalise_unit

    assert _normalise_unit("mmol/L.") == "mmol/l"
    assert _normalise_unit("mg/dL,") == "mg/dl"
    assert _normalise_unit("(mmol/L)") == "mmol/l"
    assert _normalise_unit("mmol / L") == "mmol/l"
    assert _normalise_unit("ml / min / 1.73m2.") == "ml/min/1.73m2"
    assert _normalise_unit("µmol/L.") == "umol/l"
    assert _normalise_unit("furlongs/fortnight") is None
    assert _normalise_unit(None) is None


def test_mgdl_values_are_unaffected_by_the_punctuation_rule():
    result = screen_report_text("Total cholesterol 213 mg/dL, HDL 50 mg/dL.")
    values = {v["key"]: v for v in result["values"]}
    assert values["total_cholesterol"]["unit"] == "mg/dl"
    assert values["total_cholesterol"]["status"] == "high"
    assert values["hdl"]["unit"] == "mg/dl"
    assert values["hdl"]["status"] == "normal"


def test_other_analytes_at_the_end_of_a_sentence_keep_their_unit():
    result = screen_report_text("Potassium 5.6 mmol/L. HbA1c 6.4%. eGFR 26 ml/min/1.73m2.")
    values = {v["key"]: v for v in result["values"]}
    assert values["potassium"]["unit"] == "mmol/l"
    assert values["hba1c"]["unit"] == "%"
    assert values["egfr"]["unit"] == "ml/min/1.73m2"


def test_an_unmappable_unit_names_the_band_it_was_judged_against():
    """An unrecognised unit is never presented as if it were the primary one."""
    result = screen_report_text("HDL 1.2 g/L. Creatinine 1.2 mmol/kL.")
    values = {v["key"]: v for v in result["values"]}
    assert values["hdl"]["unit"] == "mg/dl"  # the band it was judged against ...
    assert "g/L (judged as mg/dl)" in values["hdl"]["unit_label"]  # ... and said so
    assert values["creatinine"]["unit_label"] == "mmol/kL (judged as mg/dl)"


def test_an_incidental_word_after_a_number_is_not_labelled_as_a_unit():
    """The caveat stays off prose: only unit-shaped tokens get it."""
    result = screen_report_text("Creatinine 1.2 today. Potassium is 4.0 mmol/L.")
    values = {v["key"]: v for v in result["values"]}
    assert "(judged as" not in values["creatinine"]["unit_label"]
    assert values["potassium"]["unit_label"] == "mmol/l"


def test_the_shared_converter_restates_a_value_in_the_analytes_primary_unit():
    from backend.lab_report import to_primary_unit

    assert to_primary_unit("hdl", 1.3, "mmol/l") == 50.271
    assert to_primary_unit("creatinine", 130, "umol/l") == 1.4706
    assert to_primary_unit("hba1c", 48, "mmol/mol") == 6.54
    assert to_primary_unit("potassium", 5.6, "meq/l") == 5.6
    assert to_primary_unit("hdl", 50, "mg/dl") == 50  # already primary
    assert to_primary_unit("hdl", 50, None) == 50  # no unit stated: assume primary
    assert to_primary_unit("ck_mb", 30, "u/l") is None  # no defined conversion


def test_the_flattened_lab_map_converts_before_the_unit_is_lost():
    """The gates read {analyte: number} with no unit, so it must be applied here.

    A mmol/L cholesterol and a µmol/L creatinine used to reach the medication
    gates and the risk scores as bare numbers — read as mg/dL, both.
    """
    from backend.lab_report import labs_for_review

    labs = labs_for_review(
        "Total cholesterol 5.5 mmol/L, HDL 1.3 mmol/L, LDL 4.2 mmol/L, triglycerides 2.1 mmol/L. "
        "Creatinine 130 umol/L. HbA1c 48 mmol/mol. Potassium 5.6 meq/L. Troponin I 90 ng/L."
    )
    assert labs["total_cholesterol"] == 212.685
    assert labs["hdl"] == 50.271
    assert labs["ldl"] == 162.414
    assert labs["triglycerides"] == 185.997
    assert labs["creatinine"] == 1.4706
    assert labs["hba1c"] == 6.54  # IFCC -> DCCT, not a factor
    assert labs["potassium"] == 5.6  # meq/L is mmol/L
    assert labs["troponin"] == 0.09  # ng/L -> ng/mL
    # mg/dL input is untouched.
    assert labs_for_review("Total cholesterol 213 mg/dL")["total_cholesterol"] == 213


def test_a_value_in_a_unit_with_no_conversion_is_left_out_not_relabelled():
    """CK-MB in U/L has no ng/mL factor: the gates get nothing rather than 30."""
    from backend.lab_report import labs_for_review

    assert "ck_mb" not in labs_for_review("CK-MB 30 U/L")
    # Troponin is the exception: its abnormal flag still reaches the gate.
    flagged = labs_for_review("Troponin I 500 pg/mL")
    assert "troponin" not in flagged
    assert flagged["troponin_flag"] == 1.0

# ---------------------------------------------------------------------------
# How a value is written: the comma, and the unit token beside it
# ---------------------------------------------------------------------------

def test_a_decimal_comma_is_a_whole_value_not_a_stray_digit():
    """Half the world writes 1,3 mmol/L; both the unit and the value must survive.

    The unit token was allowed to start with a digit, so "HDL 1,3 mmol/L" read
    the "3" as the unit — the search matched the digit before it could reach the
    mmol/L beside it, the lookup missed and the value fell back to mg/dL. The
    digits after the comma were dropped at the same time, so the number was 1.0
    rather than 1.3. Both halves of that are asserted here.
    """
    result = screen_report_text("HDL 1,3 mmol/L")
    value = next(v for v in result["values"] if v["key"] == "hdl")
    assert value["unit"] == "mmol/l"
    assert value["unit_label"] == "mmol/l"
    assert value["value"] == 1.3
    assert value["status"] == "normal"
    assert value["reference"] == "≥1.0 mmol/l"


def test_a_comma_written_lipid_panel_keeps_every_value_unit_and_band():
    """The comma is a decimal point, so the band it is graded against is the right one."""
    cases = [
        ("Total cholesterol 5,5 mmol/L", "total_cholesterol", 5.5, "high", "≤5.2 mmol/l"),
        ("LDL 3,45 mmol/L", "ldl", 3.45, "high", "≤3.4 mmol/l"),
        ("Triglycerides 2,1 mmol/L", "triglycerides", 2.1, "high", "≤1.7 mmol/l"),
        ("HDL: 1,3 mmol/l.", "hdl", 1.3, "normal", "≥1.0 mmol/l"),
        ("Potassium 5,6 mmol/L", "potassium", 5.6, "high", "3.5–5.1 mmol/l"),
    ]
    for text, key, want_value, want_status, want_reference in cases:
        value = next(v for v in screen_report_text(text)["values"] if v["key"] == key)
        assert value["value"] == want_value, text
        assert value["unit"] == "mmol/l", text
        assert value["status"] == want_status, text
        assert value["reference"] == want_reference, text


def test_a_group_separator_after_a_comma_is_not_read_as_a_decimal_point():
    """A three-digit group is ambiguous, so it is left alone rather than guessed.

    "1,250" is a grouped thousand in one convention and 1.25 in another. The
    comma counts as a decimal point only when one or two digits follow it, so
    the parser invents neither reading; what a value like this still loses is
    recorded here rather than hidden.
    """
    value = next(
        v for v in screen_report_text("Total cholesterol 1,250 mg/dL")["values"]
        if v["key"] == "total_cholesterol"
    )
    assert value["value"] == 1.0
    assert value["unit"] == "mg/dl"


def test_a_micro_sign_before_mol_belongs_to_the_unit():
    """Printouts write µmol/L and μmol/L, not the ASCII "umol".

    The token used to begin at the first ASCII letter, so "µmol/L" was read as
    "mol/L", missed the lookup table and was judged against the mg/dL band: a
    creatinine of 130 µmol/L came back as 130 mg/dL, a critical value three
    orders of magnitude from the truth.
    """
    for text in ("Creatinine 130 µmol/L", "Creatinine 130 μmol/L"):
        value = next(v for v in screen_report_text(text)["values"] if v["key"] == "creatinine")
        assert value["unit"] == "umol/l", text
        assert value["unit_label"] == "umol/l", text
        assert value["value"] == 130.0, text
        assert value["reference"] == "53.0–115.0 umol/l", text
        assert value["status"] == "high", text  # above the band, not a critical 130 mg/dL


def test_a_comma_written_panel_reaches_the_gates_in_primary_units():
    """The flattened lab map has no unit, so the comma must be read before it is lost."""
    from backend.lab_report import labs_for_review

    labs = labs_for_review(
        "Total cholesterol 5,5 mmol/L. HDL 1,3 mmol/L. LDL 3,45 mmol/L. "
        "Creatinine 130 µmol/L."
    )
    assert labs["total_cholesterol"] == 212.685  # 5.5 x 38.67
    assert labs["hdl"] == 50.271
    assert labs["ldl"] == 133.4115
    assert labs["creatinine"] == 1.4706


def test_a_bare_number_is_a_value_when_it_ends_a_sentence():
    """The dose guard's boundary, which the unit token no longer decides.

    A number with nothing after it is a dose ("start aspirin 5"); one that ends
    a sentence states a value ("eGFR 26."). The sentence period was matched as
    the unit token by accident, which is what let the second case through, so
    the boundary is asserted here and the renal gate keeps seeing the eGFR.
    """
    from backend.lab_report import labs_for_review

    assert screen_report_text("cholesterol 40").get("values") == []
    assert screen_report_text("start aspirin 5").get("values") == []
    result = screen_report_text("eGFR 26. Potassium 6.1 mmol/L.")
    egfr = next(v for v in result["values"] if v["key"] == "egfr")
    assert (egfr["value"], egfr["unit"], egfr["status"]) == (26.0, "ml/min/1.73m2", "low")
    # The path the FHIR export and the metformin gate take.
    assert labs_for_review("Troponin I: 0.09 ng/mL. Potassium 6.1 mmol/L. eGFR 26.")["egfr"] == 26.0

# ---------------------------------------------------------------------------
# Lipid abbreviations, and the labels they hide inside
# ---------------------------------------------------------------------------

def test_every_lipid_abbreviation_is_read_as_its_own_fraction():
    """Chol, TG, HDL-C, LDL-C and non-HDL are the panel's written forms.

    Each case asserts the value is attributed to that fraction *and to nothing
    else*, which is the half that used to go wrong: "non-HDL" was reported as a
    healthy HDL, and "LDL cholesterol 120" as both LDL and a total of 120.
    """
    cases = [
        ("Chol: 5.5 mmol/L", "total_cholesterol", 5.5, "mmol/l"),
        ("Total chol 5.5 mmol/L", "total_cholesterol", 5.5, "mmol/l"),
        ("T. chol 250 mg/dL", "total_cholesterol", 250.0, "mg/dl"),
        ("TG 2.1 mmol/L", "triglycerides", 2.1, "mmol/l"),
        ("TGs 2.1 mmol/L", "triglycerides", 2.1, "mmol/l"),
        ("HDL-C 1.2 mmol/L", "hdl", 1.2, "mmol/l"),
        ("LDL-C 3.4 mmol/L", "ldl", 3.4, "mmol/l"),
        ("non-HDL 4.2 mmol/L", "non_hdl", 4.2, "mmol/l"),
        ("non-HDL-C 5,0 mmol/L", "non_hdl", 5.0, "mmol/l"),
        ("nonHDL 5.0 mmol/L", "non_hdl", 5.0, "mmol/l"),
        ("Non-HDL cholesterol 5.0 mmol/L", "non_hdl", 5.0, "mmol/l"),
        ("non high density lipoprotein 5.0 mmol/L", "non_hdl", 5.0, "mmol/l"),
    ]
    for text, key, want_value, want_unit in cases:
        found = [(v["key"], v["value"], v["unit"]) for v in screen_report_text(text)["values"]]
        assert found == [(key, want_value, want_unit)], text


def test_a_lipid_abbreviation_is_not_matched_inside_a_longer_word():
    """A word, not a substring: cholestasis is not a cholesterol."""
    assert [v["key"] for v in screen_report_text("cholestasis noted, triglycerides 2.1 mmol/L")["values"]] == [
        "triglycerides"
    ]
    assert screen_report_text("cholesteryl ester 40 mg/dL").get("values") == []
    # "cholesterol" is its own alias, and the bare "chol" must not add a second entry.
    assert len(screen_report_text("Total cholesterol 5.5 mmol/L")["values"]) == 1


def test_a_lipoprotein_cholesterol_is_not_also_read_as_total_cholesterol():
    """"LDL cholesterol 120 mg/dL" states one fraction, not two.

    The word "cholesterol" belongs to the fraction named in front of it, so the
    total-cholesterol alias must not claim the same number again — which it did,
    reporting a total of 45 mg/dL from "HDL cholesterol 45". VLDL has no band
    here, so its number is reported as nothing rather than folded into the total.
    """
    values = screen_report_text(
        "LDL cholesterol 120 mg/dL. HDL cholesterol 45 mg/dL. "
        "VLDL cholesterol 30 mg/dL. very low density lipoprotein cholesterol 28 mg/dL."
    )["values"]
    assert {v["key"]: v["value"] for v in values} == {"ldl": 120.0, "hdl": 45.0}


def test_non_hdl_is_graded_against_its_own_band_not_hdls():
    """Read as HDL, a high non-HDL came back "normal" — the finding inverted.

    Non-HDL cholesterol is total minus HDL, and the international convention puts
    its threshold 30 mg/dL (0.8 mmol/L) above the LDL-C threshold, so the band
    here is LDL's 130/190 mg/dL shifted to 160/220 (4.2/5.7 mmol/L).
    """
    high = screen_report_text("non-HDL-C 5.0 mmol/L")["values"]
    assert [v["key"] for v in high] == ["non_hdl"]  # not an HDL value at all
    assert (high[0]["status"], high[0]["reference"]) == ("high", "≤4.2 mmol/l")

    statuses = {
        text: screen_report_text(text)["values"][0]["status"]
        for text in ("non-HDL 160 mg/dL", "non-HDL 190 mg/dL", "non-HDL 230 mg/dL")
    }
    assert statuses == {
        "non-HDL 160 mg/dL": "normal",
        "non-HDL 190 mg/dL": "high",
        "non-HDL 230 mg/dL": "critical_high",
    }


def test_the_lipid_abbreviations_reach_the_gates_in_primary_units():
    """The flattened lab map is judged in mg/dL, so the panel's short forms convert too."""
    from backend.lab_report import labs_for_review

    labs = labs_for_review("non-HDL 5.0 mmol/L. Total chol 5.5 mmol/L. TGs 2.1 mmol/L.")
    assert labs["non_hdl"] == 193.35  # 5.0 x 38.67, the same factor as cholesterol
    assert labs["total_cholesterol"] == 212.685
    assert labs["triglycerides"] == 185.997
