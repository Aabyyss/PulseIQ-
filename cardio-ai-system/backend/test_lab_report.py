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
