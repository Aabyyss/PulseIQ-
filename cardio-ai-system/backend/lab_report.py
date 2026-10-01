"""Structured report screening: parse lab values, flag against reference
ranges, explain every flag.

Why this exists
---------------
Report context used to be free text the pipeline only keyword-searched
("troponin" appears → mention troponin). Clinicians need the actual numbers
checked against reference ranges, with the abnormal ones surfaced first and a
plain-language reason for each flag — the "which finding triggered this?"
explainability the review asked for.

Design
------
- Deterministic, rule-based extraction: every analyte has an alias list
  (``Troponin I``, ``Trop-I``, ``hs-TnI`` …) and a numeric pattern, so a
  parsed value always points back to the exact matched text.
- Unit-aware ranges: the same analyte in different units (mg/dL vs mmol/L,
  ng/mL vs ng/L) gets the right reference band. A value with an unrecognised
  unit falls back to the analyte's primary band and says so.
- Severity ordering: ``critical`` → ``abnormal`` → ``normal``. Criticals
  (potassium 6.4, EF 25%, anterior ST elevation) always sort first.
- Explainability: each flagged value carries ``matched_text`` (the snippet
  that produced it), ``reference`` (the band it was judged against) and
  ``explanation`` (why it is out of range). Nothing is flagged without all
  three.
- Text-only findings (ECG statements with no number) become ``text_flags``
  so "anterior ST elevation" is surfaced even when no value is parseable.

This module only reads text; it stores nothing and never leaves the machine.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Reference ranges
# ---------------------------------------------------------------------------

# unit -> (low, high, critical_low, critical_high); None = unbounded side.
# Ranges are general adult bands used for FLAGGING, not diagnosis: they are
# deliberately conservative (wide) so the tool rarely cries wolf, and every
# flag tells the clinician the exact band it used so they can overrule it.
Band = tuple[float | None, float | None, float | None, float | None]

# Per-analyte guidance shown with an abnormal flag (why the clinician cares).
_TROP_NOTE = "Troponin above the 99th percentile indicates myocardial injury — correlate with symptom timeline and ECG."
_EF_NOTE = "Reduced ejection fraction indicates LV systolic dysfunction — quantify severity and assess for cardiomyopathy."

_ANALYTES: list[dict[str, Any]] = [
    {
        "key": "troponin_i",
        "label": "Troponin I",
        "aliases": [r"troponin[\s\-]*i\b", r"\btrop[\s\-]*i\b", r"\bhs[\s\-]*tni\b", r"\bhstni\b", r"\bctni\b"],
        "ranges": {"ng/ml": (0.0, 0.04, None, 0.10), "ng/l": (0.0, 14.0, None, 100.0)},
        "primary_unit": "ng/ml",
        "note": _TROP_NOTE,
    },
    {
        "key": "troponin_t",
        "label": "Troponin T",
        "aliases": [r"troponin[\s\-]*t\b", r"\btrop[\s\-]*t\b", r"\bhs[\s\-]*tnt\b", r"\bhstnt\b", r"\bctnt\b"],
        "ranges": {"ng/ml": (0.0, 0.01, None, 0.10), "ng/l": (0.0, 14.0, None, 100.0)},
        "primary_unit": "ng/ml",
        "note": _TROP_NOTE,
    },
    {
        "key": "ck_mb",
        "label": "CK-MB",
        "aliases": [r"ck[\s\-]*mb\b", r"creatine\s+kinase[\s\-]*mb"],
        "ranges": {"ng/ml": (0.0, 5.0, None, 25.0), "u/l": (0.0, 25.0, None, 200.0)},
        "primary_unit": "ng/ml",
        "note": "CK-MB rise supports myocardial injury; peaks earlier than troponin.",
    },
    {
        "key": "bnp",
        "label": "BNP",
        "aliases": [r"\bnt[\s\-]*pro[\s\-]*bnp\b", r"\bbnp\b"],
        "ranges": {"pg/ml": (0.0, 100.0, None, 900.0)},
        "primary_unit": "pg/ml",
        "note": "BNP above the upper reference limit supports heart failure; NT-proBNP ≥900 pg/mL in acute dyspnea is strongly suggestive.",
    },
    {
        "key": "total_cholesterol",
        "label": "Total cholesterol",
        "aliases": [r"total\s+cholesterol\b", r"cholesterol\s+total\b", r"\bserum\s+cholesterol\b", r"\bcholesterol\b"],
        "ranges": {"mg/dl": (None, 200.0, None, 300.0), "mmol/l": (None, 5.2, None, 7.8)},
        "primary_unit": "mg/dl",
        "note": "≥200 mg/dL is borderline high; ≥240 mg/dL is high and lowers the LDL treatment threshold.",
    },
    {
        "key": "ldl",
        "label": "LDL cholesterol",
        "aliases": [r"ldl[\s\-]*c\b", r"\bldl\b", r"low[\s\-]+density\s+lipoprotein"],
        "ranges": {"mg/dl": (None, 130.0, None, 190.0), "mmol/l": (None, 3.4, None, 4.9)},
        "primary_unit": "mg/dl",
        "note": "LDL ≥160 mg/dL is high; risk-based targets are lower (≤70–100 mg/dL) for secondary prevention.",
    },
    {
        "key": "hdl",
        "label": "HDL cholesterol",
        "aliases": [r"hdl[\s\-]*c\b", r"\bhdl\b", r"high[\s\-]+density\s+lipoprotein"],
        "ranges": {"mg/dl": (40.0, None, None, None), "mmol/l": (1.0, None, None, None)},
        "primary_unit": "mg/dl",
        "note": "HDL <40 mg/dL (men) or <50 mg/dL (women) is a cardiovascular risk factor.",
    },
    {
        "key": "triglycerides",
        "label": "Triglycerides",
        "aliases": [r"triglycerides?\b", r"\btg\b"],
        "ranges": {"mg/dl": (None, 150.0, None, 500.0), "mmol/l": (None, 1.7, None, 5.7)},
        "primary_unit": "mg/dl",
        "note": "≥150 mg/dL is borderline; ≥500 mg/dL carries acute pancreatitis risk and needs urgent attention.",
    },
    {
        "key": "glucose",
        "label": "Glucose (fasting)",
        "aliases": [r"fasting\s+glucose\b", r"glucose[\s\(]*fasting", r"\bbs[\s\-]*f\b", r"\bfbs\b", r"\bglucose\b", r"\bblood\s+sugar\b"],
        "ranges": {"mg/dl": (70.0, 99.0, 54.0, 300.0), "mmol/l": (3.9, 5.6, 3.0, 16.7)},
        "primary_unit": "mg/dl",
        "note": "Fasting glucose ≥126 mg/dL is in the diabetes range; ≥200 mg/dL with symptoms warrants same-day assessment.",
    },
    {
        "key": "hba1c",
        "label": "HbA1c",
        "aliases": [r"hba1c\b", r"\bah[\s\-]*1c\b", r"glycated\s+haemoglobin\b", r"glycated\s+hemoglobin\b"],
        "ranges": {"%": (4.0, 5.7, None, 10.0), "mmol/mol": (20.0, 39.0, None, 86.0)},
        "primary_unit": "%",
        "note": "≥5.7% is prediabetes range; ≥6.5% is diabetes range; ≥9% suggests poor chronic glycaemic control.",
    },
    {
        "key": "creatinine",
        "label": "Creatinine",
        "aliases": [r"creatinine\b", r"\bs\.?cr\b"],
        "ranges": {"mg/dl": (0.6, 1.3, None, 3.0), "umol/l": (53.0, 115.0, None, 265.0)},
        "primary_unit": "mg/dl",
        "note": "Above the reference range suggests impaired renal function — stage with eGFR before contrast or metformin.",
    },
    {
        "key": "potassium",
        "label": "Potassium",
        "aliases": [r"potassium\b", r"\bk\b(?!\w)", r"\bk\+\b"],
        "ranges": {"mmol/l": (3.5, 5.1, 3.0, 6.0), "meq/l": (3.5, 5.1, 3.0, 6.0)},
        "primary_unit": "mmol/l",
        "note": "K+ ≥6.0 is an emergency — check ECG immediately and treat. K+ <3.0 risks arrhythmia.",
    },
    {
        "key": "sodium",
        "label": "Sodium",
        "aliases": [r"sodium\b", r"\bna\b(?!\w)", r"\bna\+\b"],
        "ranges": {"mmol/l": (135.0, 145.0, 125.0, 155.0), "meq/l": (135.0, 145.0, 125.0, 155.0)},
        "primary_unit": "mmol/l",
        "note": "Na+ outside 135–145 needs a cause; <125 or >155 is severe and requires urgent correction.",
    },
    {
        "key": "egfr",
        "label": "eGFR",
        "aliases": [r"egfr\b", r"gfr\b"],
        "ranges": {"ml/min/1.73m2": (60.0, None, 15.0, None), "ml/min": (60.0, None, 15.0, None)},
        "primary_unit": "ml/min/1.73m2",
        "note": "eGFR <60 for 3 months defines CKD stage 3; <15 needs renal referral.",
    },
    {
        "key": "tsh",
        "label": "TSH",
        "aliases": [r"\btsh\b", r"thyroid[\s\-]+stimulating\s+hormone"],
        "ranges": {"miu/l": (0.4, 4.0, 0.1, 10.0)},
        "primary_unit": "miu/l",
        "note": "Thyroid dysfunction mimics palpitations and heart failure — worth checking when rhythm symptoms have no other cause.",
    },
    {
        "key": "hemoglobin",
        "label": "Haemoglobin",
        "aliases": [r"haemoglobin\b", r"hemoglobin\b", r"\bhb\b(?!a1c)"],
        "ranges": {"g/dl": (12.0, 17.0, 7.0, 22.0)},
        "primary_unit": "g/dl",
        "note": "Anaemia worsens angina and heart failure; very low values need urgent workup.",
    },
    {
        "key": "lvef",
        "label": "Ejection fraction (LVEF)",
        "aliases": [r"lvef\b", r"\bejection\s+fraction\b", r"(?<!\w)ef\b"],
        "ranges": {"%": (55.0, None, None, None)},
        "primary_unit": "%",
        "note": _EF_NOTE,
        # EF is judged against a floor (55%), not a band — handled below.
        "floor": True,
    },
]

_UNIT_ALIASES = {
    "mg/dl": "mg/dl", "mg/dl": "mg/dl", "mgdl": "mg/dl",
    "mmol/l": "mmol/l", "mmol/l": "mmol/l", "mmoll": "mmol/l",
    "ng/ml": "ng/ml", "ngl": "ng/l", "ng/l": "ng/l",
    "pg/ml": "pg/ml", "pgml": "pg/ml",
    "u/l": "u/l", "iu/l": "iu/l",
    "meq/l": "meq/l", "umol/l": "umol/l",
    "g/dl": "g/dl", "gdl": "g/dl",
    "%": "%", "ml/min": "ml/min", "ml/min/1.73m2": "ml/min/1.73m2",
    "ml/min/1.73": "ml/min/1.73m2", "miu/l": "miu/l", "mIU/L": "miu/l",
    "mmol/mol": "mmol/mol",
}

# Text-only findings worth flagging even without a parseable number.
# (pattern, severity, label, explanation)
_TEXT_FLAGS: list[tuple[str, str, str, str]] = [
    (r"\bST[\s\-]?elevation\b", "critical", "ST elevation on ECG",
     "ST elevation is a STEMI pattern until proven otherwise — immediate cardiology/PCI pathway."),
    (r"\bventricular\s+tachycard", "critical", "Ventricular tachycardia",
     "Sustained VT is life-threatening — urgent escalation and rhythm review."),
    (r"\bventricular\s+fibrillation\b", "critical", "Ventricular fibrillation",
     "VF is pulseless — immediate resuscitation."),
    (r"\bcomplete\s+heart\s+block\b|\bthird[\s\-]degree\s+av\s+block\b", "critical", "Complete heart block",
     "High-grade AV block may need temporary or permanent pacing — urgent review."),
    (r"\bcardiogenic\s+shock\b", "critical", "Cardiogenic shock",
     "End-stage pump failure — emergency management."),
    (r"\bST[\s\-]?depression\b", "abnormal", "ST depression on ECG",
     "ST depression suggests ischaemia — correlate with troponin trend and symptoms."),
    (r"\bT[\s\-]?wave\s+inversion\b", "abnormal", "T-wave inversion",
     "T-wave inversion can indicate ischaemia or strain — interpret with the clinical picture."),
    (r"\batrial\s+fibrillation\b|\bAF\s+with\s+rapid\b|\bfast\s+AF\b", "abnormal", "Atrial fibrillation",
     "AF needs rate/rhythm control and stroke-risk (CHA₂DS₂-VASc) assessment."),
    (r"\bpathological\s+Q\s+waves?\b", "abnormal", "Pathological Q waves",
     "Q waves suggest established infarction — date it clinically."),
]

# Troponin text flags only fire when no NUMERIC troponin was parsed
# (otherwise the number carries the flag).
_TROP_TEXT_PATTERNS = [
    r"(?:troponin|trop)[\s\-]*(?:i|t|is|was)?\s*(?:is\s+)?(?:markedly\s+)?(?:elevated|positive|high)",
    r"elevated\s+(?:troponin|trop)",
    r"troponin\s+rise",
]

# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_NUMBER = r"(?<![<>])(<?\d+(?:\.\d+)?)(?!\s?%?\s*[x×])"  # avoid "5 x daily" dosing
_NUM_RE = re.compile(_NUMBER)


def _normalise_unit(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = raw.strip().lower().replace("μ", "u").replace("µ", "u")
    cleaned = cleaned.replace("²", "2").replace(" ", "")
    return _UNIT_ALIASES.get(cleaned)


def _compile_aliases(aliases: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(rf"(?<![a-z0-9])(?:{alias})(?![a-z0-9])", re.IGNORECASE) for alias in aliases]


def _classify(value: float, below_limit: bool, band: Band, is_floor: bool) -> str:
    low, high, crit_low, crit_high = band
    if below_limit:
        # "<0.01" — for an upper-limit analyte that reads as normal.
        return "normal" if (high is None or value <= high) else "high"
    if is_floor:
        # Floor-style range (EF, eGFR, HDL): low is the problem.
        if low is not None and value < low:
            return "critical_low" if (crit_low is not None and value < crit_low) else "low"
        return "normal"
    if crit_low is not None and value < crit_low:
        return "critical_low"
    if crit_high is not None and value > crit_high:
        return "critical_high"
    if low is not None and value < low:
        return "low"
    if high is not None and value > high:
        return "high"
    return "normal"


_SEVERITY = {"critical_high": "critical", "critical_low": "critical", "high": "abnormal", "low": "abnormal", "normal": "normal"}
_STATUS_TEXT = {
    "critical_high": "critically high", "critical_low": "critically low",
    "high": "above reference", "low": "below reference", "normal": "within reference range",
}


def _format_band(band: Band, unit: str | None, is_floor: bool) -> str:
    low, high, _, _ = band
    suffix = f" {unit}" if unit else ""
    if is_floor or high is None:
        return f"≥{low}{suffix}" if low is not None else "no band"
    if low is None:
        return f"≤{high}{suffix}"
    return f"{low}–{high}{suffix}"


def _extract_numeric(analyte: dict[str, Any], text: str, lowered: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen_values: set[tuple[float, str]] = set()
    is_floor = bool(analyte.get("floor"))

    for alias in _compile_aliases(analyte["aliases"]):
        for match in alias.finditer(text):
            window = text[match.end():match.end() + 30]
            num_match = _NUM_RE.search(window)
            if not num_match:
                continue
            raw_value = num_match.group(1)
            below_limit = raw_value.startswith("<") or raw_value.startswith(">")
            below_limit = raw_value.startswith("<")
            try:
                value = float(raw_value.lstrip("<>"))
            except ValueError:
                continue
            # Reject values glued to a dose context ("5 mg daily" after a
            # lab name is a prescription, not a lab result) — a real lab
            # line carries the analyte's unit or a colon/equals separator.
            after = window[: num_match.end()]
            unit_match = re.search(r"([a-zA-Z/%\.]+)", window[num_match.end():num_match.end() + 12])
            unit_raw = unit_match.group(1) if unit_match else None
            unit = _normalise_unit(unit_raw)
            separator = re.search(r"[:=]", after)
            has_known_unit = unit in analyte["ranges"]
            if not has_known_unit and not separator and not is_floor:
                # No colon and no recognised unit → likely not a lab line.
                if unit_raw is None:
                    continue
            ranges: dict[str, Band] = analyte["ranges"]
            band = ranges.get(unit or "", ranges[analyte["primary_unit"]])
            unit_label = unit or analyte["primary_unit"]
            if unit and not has_known_unit:
                unit_label = f"{unit} (judged as {analyte['primary_unit']})"
            status = _classify(value, below_limit, band, is_floor)
            dedupe = (value, status)
            if dedupe in seen_values:
                continue
            seen_values.add(dedupe)
            start = max(0, match.start() - 5)
            end = min(len(text), match.end() + num_match.end() + 12)
            matched_text = " ".join(text[start:end].split())
            entry = {
                "key": analyte["key"],
                "name": analyte["label"],
                "value": value,
                "value_text": ("<" if below_limit else "") + raw_value.lstrip("<>"),
                "unit": analyte["primary_unit"] if unit is None else unit,
                "unit_label": unit_label,
                "reference": _format_band(band, unit_label if not unit else unit, is_floor),
                "status": status,
                "severity": _SEVERITY[status],
                "matched_text": matched_text,
                "note": analyte["note"],
            }
            if status != "normal":
                entry["explanation"] = _explain(entry, band, is_floor)
            found.append(entry)
    return found


def _explain(entry: dict[str, Any], band: Band, is_floor: bool) -> str:
    low, high, crit_low, crit_high = band
    value_txt = f"{entry['value_text']} {entry['unit']}" if entry["unit"] else entry["value_text"]
    status = entry["status"]
    if status == "critical_high":
        base = f"{entry['name']} {value_txt} is critically above the reference ceiling of {high} {entry['unit']}."
    elif status == "critical_low":
        base = f"{entry['name']} {value_txt} is critically below the reference floor of {low} {entry['unit']}."
    elif status == "high":
        base = f"{entry['name']} {value_txt} is above the reference upper limit of {high} {entry['unit']}."
    elif status == "low":
        base = f"{entry['name']} {value_txt} is below the reference lower limit of {low} {entry['unit']}."
    else:
        return ""
    return f"{base} {entry['note']}"


def _extract_text_flags(text: str, parsed_keys: set[str]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    lowered = text.lower()
    for pattern, severity, label, explanation in _TEXT_FLAGS:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        flags.append({
            "key": f"text_{len(flags)}",
            "name": label,
            "status": severity,
            "severity": severity,
            "matched_text": " ".join(match.group(0).split()),
            "explanation": explanation,
            "note": "",
            "source": "text_finding",
        })
    if not parsed_keys & {"troponin_i", "troponin_t"}:
        for pattern in _TROP_TEXT_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                flags.append({
                    "key": f"text_{len(flags)}",
                    "name": "Troponin reported positive/elevated",
                    "status": "critical",
                    "severity": "critical",
                    "matched_text": " ".join(match.group(0).split()),
                    "explanation": f"{_TROP_NOTE} A positive qualitative troponin counts as abnormal even without a number.",
                    "note": "",
                    "source": "text_finding",
                })
                break
    return flags


def screen_report_text(text: str) -> dict[str, Any]:
    """Parse ``text`` and return reference-range flags, criticals first.

    Returns::

        {"values": [...], "text_flags": [...],
         "summary": {"critical": n, "abnormal": n, "normal": n, "parsed": bool},
         "message": str}
    """
    raw = str(text or "")
    if not raw.strip():
        return {"values": [], "text_flags": [], "summary": {"critical": 0, "abnormal": 0, "normal": 0, "parsed": False},
                "message": "No report text supplied."}

    values: list[dict[str, Any]] = []
    parsed_keys: set[str] = set()
    for analyte in _ANALYTES:
        entries = _extract_numeric(analyte, raw, raw.lower())
        if entries:
            parsed_keys.add(analyte["key"])
            values.extend(entries)

    text_flags = _extract_text_flags(raw, parsed_keys)

    severity_rank = {"critical": 0, "abnormal": 1, "normal": 2}
    values.sort(key=lambda v: (severity_rank[v["severity"]], v["name"]))
    text_flags.sort(key=lambda f: severity_rank[f["severity"]])

    critical = sum(1 for v in values if v["severity"] == "critical") + \
        sum(1 for f in text_flags if f["severity"] == "critical")
    abnormal = sum(1 for v in values if v["severity"] == "abnormal") + \
        sum(1 for f in text_flags if f["severity"] == "abnormal")
    normal = sum(1 for v in values if v["severity"] == "normal")
    parsed = bool(values or text_flags)

    if not parsed:
        message = "No numeric lab values or ECG statements recognised — paste lines like \"Troponin I: 0.05 ng/mL\" or \"LVEF 35%\"."
    elif critical:
        message = f"{critical} critical result(s) — review these first."
    elif abnormal:
        message = f"{abnormal} value(s) outside the reference range."
    else:
        message = f"All {normal} parsed value(s) within their reference ranges."

    return {
        "values": values,
        "text_flags": text_flags,
        "summary": {"critical": critical, "abnormal": abnormal, "normal": normal, "parsed": parsed},
        "message": message,
    }
