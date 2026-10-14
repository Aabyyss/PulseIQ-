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
  (``Troponin I``, ``Trop-I``, ``hs-TnI`` …, ``Chol``, ``TG``, ``non-HDL``) and a
  numeric pattern, so a parsed value always points back to the exact matched
  text. Aliases match whole words, and a name that contains another fraction's
  name is resolved by the label around the match — the "cholesterol" in "LDL
  cholesterol" belongs to LDL, and "non-HDL" is neither HDL nor the total.
  See ADR-022.
- Unit-aware ranges: the same analyte in different units (mg/dL vs mmol/L,
  ng/mL vs ng/L) gets the right reference band, whatever punctuation follows the
  token ("... 1.3 mmol/L." is mmol/L, not mg/dL) and however the unit is
  printed — the micro sign of "µmol/L" belongs to the unit, not to the letters
  after it. A value written with a decimal comma ("HDL 1,3 mmol/L") is read as
  1.3 in the unit beside it, though a three-digit group after the comma
  ("1,250") is left alone, being ambiguous between the two conventions. A value
  whose printed unit cannot be mapped is judged against the analyte's primary
  band and labelled with the unit it was actually read as, so no band is
  assumed silently.
- Derived lipids, labelled as derived: the three lipid fractions are not
  independent — ``non-HDL = total cholesterol - HDL`` and, the same identity
  rearranged, ``HDL = total cholesterol - non-HDL`` — so a panel that prints two
  of them states the third. It is worked out from the printed pair and returned
  as a value of its own with ``computed: true`` and the arithmetic that produced
  it, so nothing a clinician reads as printed was in fact inferred. See ADR-023.
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
        # "Chol" is how a printout labels the total; the boundary keeps it out of
        # "cholesterol", "cholestasis" and "cholesteryl".
        "aliases": [r"total\s+cholesterol\b", r"cholesterol\s+total\b", r"\bserum\s+cholesterol\b", r"\bcholesterol\b", r"\bchol\b"],
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
        "aliases": [r"triglycerides?\b", r"\btgs?\b"],
        "ranges": {"mg/dl": (None, 150.0, None, 500.0), "mmol/l": (None, 1.7, None, 5.7)},
        "primary_unit": "mg/dl",
        "note": "≥150 mg/dL is borderline; ≥500 mg/dL carries acute pancreatitis risk and needs urgent attention.",
    },
    {
        # Non-HDL is total minus HDL, so it needs its own band: graded against
        # HDL's floor (or against the total's ceiling) a high value would read as
        # normal, which is the opposite of the finding.
        "key": "non_hdl",
        "label": "Non-HDL cholesterol",
        "aliases": [
            r"non[\s\-]*hdl[\s\-]*c\b",
            r"non[\s\-]*hdl\b",
            r"non[\s\-]+high[\s\-]+density[\s\-]+lipoprotein",
        ],
        # The international convention sets the non-HDL threshold 30 mg/dL
        # (0.8 mmol/L) above the LDL-C threshold, so this is LDL's band shifted:
        # 130/190 -> 160/220 mg/dL and 3.4/4.9 -> 4.2/5.7 mmol/L.
        "ranges": {"mg/dl": (None, 160.0, None, 220.0), "mmol/l": (None, 4.2, None, 5.7)},
        "primary_unit": "mg/dl",
        "note": "Non-HDL cholesterol is total minus HDL; its threshold sits 30 mg/dL (0.8 mmol/L) above the LDL-C threshold.",
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

# The analytes a derived value can belong to, by key (bands, labels and notes
# live on the analyte entry, so a computed fraction is banded like a printed one).
_ANALYTE_BY_KEY: dict[str, dict[str, Any]] = {analyte["key"]: analyte for analyte in _ANALYTES}

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

# A value: an integer with an optional decimal part, written with either a dot
# or — as much of the world writes it — a comma. A comma counts as a decimal
# point only when one or two digits follow it and no third does, so a printed
# group separator ("platelets 250,000") still leaves the integer alone instead
# of quietly shrinking it by three orders of magnitude.
_NUMBER = r"(?<![<>])(<?\d+(?:\.\d+|,\d{1,2}(?!\d))?)(?!\s?%?\s*[x×])"  # avoid "5 x daily" dosing
_NUM_RE = re.compile(_NUMBER)

# The unit token printed after a value. The FIRST character must be a letter or
# the micro sign, never a digit: a token that starts with a digit is part of the
# *value*, and letting one through made a European decimal comma swallow the
# unit — "HDL 1,3 mmol/L" read "3" as the token, missed the lookup table and
# fell back to mg/dL, discarding the mmol/L printed right beside it. Digits, dots
# and slashes stay in the continuation class so "ml/min/1.73m2" is one token, the
# micro sign is included because units are printed with it ("µmol/L"), and the
# optional slash group keeps a spaced "mmol / L" together; sentence punctuation
# is trimmed by ``_normalise_unit`` rather than excluded here, because a trailing
# period must not swallow the unit that precedes it.
_UNIT_TOKEN_RE = re.compile(
    r"[a-zA-Z\u00b5\u03bc/%][a-zA-Z0-9/%\u00b5\u03bc\.]*(?:\s*/\s*[a-zA-Z0-9\.]+)?"
)

# Stems that make a printed token look like a unit rather than a prose word, so
# the "judged as" caveat is attached to "g/l" and "mmol/kL" without also
# labelling every incidental word after a number.
_UNIT_STEMS = ("mmol", "umol", "mg", "ng", "pg", "meq", "miu", "iu", "ml", "g", "u")


def _clean_unit_text(raw: str | None) -> str:
    return (raw or "").strip().strip(".,;:()[]")


def _looks_like_unit(raw: str | None) -> bool:
    token = _clean_unit_text(raw).lower().replace("μ", "u").replace("µ", "u")
    if not token:
        return False
    if "/" in token:
        return True
    return token.startswith(_UNIT_STEMS)


def _normalise_unit(raw: str | None) -> str | None:
    """Map a printed unit token onto the canonical unit, or ``None`` if unknown.

    Running text trails the token with sentence punctuation ("... 1.3 mmol/L."),
    and a period used to be read as part of the unit, so ``mmol/l.`` missed the
    lookup table and the value silently fell back to the analyte's primary unit
    — grading a mmol/L result against the mg/dL band. Punctuation is therefore
    stripped from both ends before the lookup, and the token itself is allowed to
    span a slash ("mmol / L", "ml/min/1.73m2").
    """
    if not raw:
        return None
    cleaned = raw.strip().lower().replace("μ", "u").replace("µ", "u")
    cleaned = cleaned.replace("²", "2").replace(" ", "")
    return _UNIT_ALIASES.get(cleaned.strip(".,;:()[]"))


def _compile_aliases(aliases: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(rf"(?<![a-z0-9])(?:{alias})(?![a-z0-9])", re.IGNORECASE) for alias in aliases]


# One fraction's name contains another's. "LDL cholesterol 120 mg/dL" states LDL,
# not a total cholesterol of 120, and "non-HDL cholesterol" states neither HDL
# nor total cholesterol — read as HDL it inverts the finding, because a high
# non-HDL would look like a healthy HDL. A match is dropped when the label around
# it names a different fraction; every pattern is anchored to the end of the
# match, so it describes the candidate's own left context plus the name matched.
_CONTEXT_EXCLUDES: dict[str, str] = {
    "hdl": r"non[\s\-]+(?:hdl(?:[\s\-]*c)?|high[\s\-]+density(?:[\s\-]+lipoprotein)?(?:[\s\-]*c)?)$",
    # "very low density lipoprotein" is VLDL, not LDL, and it is the one place
    # the LDL alias fires inside another fraction's name. The prefix is required:
    # an optional one would match "LDL" on its own and drop every LDL value.
    "ldl": (
        r"(?:very[\s\-]+non[\s\-]+|very[\s\-]+|non[\s\-]+)"
        r"(?:ldl(?:[\s\-]*c)?|low[\s\-]+density(?:[\s\-]+lipoprotein)?(?:[\s\-]*c)?)$"
    ),
    "total_cholesterol": (
        r"(?:non[\s\-]+)?"
        r"(?:hdl|ldl|vldl|idl|(?:very[\s\-]+)?(?:low|high)[\s\-]+density(?:[\s\-]+lipoprotein)?)"
        r"(?:[\s\-]*c)?[\s\-]*(?:cholesterol|chol)$"
    ),
}


def _labelled_as_another_fraction(analyte: dict[str, Any], text: str, match: re.Match[str]) -> bool:
    """True when the matched name is part of a different lipid fraction's label."""
    pattern = _CONTEXT_EXCLUDES.get(analyte["key"])
    if not pattern:
        return False
    # 48 characters covers the longest label ("very low density lipoprotein
    # cholesterol") with room to spare; the anchor keeps it specific.
    label = text[max(0, match.start() - 48):match.end()]
    return re.search(pattern, label, re.IGNORECASE) is not None


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
            if _labelled_as_another_fraction(analyte, text, match):
                continue
            window = text[match.end():match.end() + 30]
            num_match = _NUM_RE.search(window)
            if not num_match:
                continue
            raw_value = num_match.group(1)
            below_limit = raw_value.startswith("<") or raw_value.startswith(">")
            below_limit = raw_value.startswith("<")
            try:
                # A comma is a decimal point here (see ``_NUMBER``); float()
                # itself only reads a dot.
                value = float(raw_value.lstrip("<>").replace(",", "."))
            except ValueError:
                continue
            # Reject values glued to a dose context ("5 mg daily" after a
            # lab name is a prescription, not a lab result) — a real lab
            # line carries the analyte's unit or a colon/equals separator.
            after = window[: num_match.end()]
            unit_match = _UNIT_TOKEN_RE.search(window[num_match.end():num_match.end() + 12])
            unit_raw = unit_match.group(0) if unit_match else None
            unit = _normalise_unit(unit_raw)
            # A printed line marks the value with a colon or equals; a spoken
            # one says "his eGFR is 26" or "a creatinine of 1.2", where the
            # number trails the sentence and has no unit token to recognise it
            # by. Both are explicit value markers.
            separator = re.search(r"[:=]|\b(?:is|are|was|were|of|at)\b", after, re.I)
            has_known_unit = unit in analyte["ranges"]
            # What follows a bare number is what separates a statement from a
            # fragment: "eGFR 26." states a value, while a number with nothing
            # after it ("start aspirin 5") is a dose. This used to fall out of
            # the unit token matching a sentence period by accident; it is
            # checked here so the token itself can reject punctuation.
            trailing = window[num_match.end():].strip()
            if not has_known_unit and not separator and not is_floor and not trailing:
                continue
            ranges: dict[str, Band] = analyte["ranges"]
            band = ranges.get(unit or "", ranges[analyte["primary_unit"]])
            unit_label = unit or analyte["primary_unit"]
            if unit and not has_known_unit:
                unit_label = f"{unit} (judged as {analyte['primary_unit']})"
            elif unit is None and _looks_like_unit(unit_raw):
                # A unit this module cannot map must not look like the primary
                # unit: name what was printed and what it was banded against.
                unit_label = f"{_clean_unit_text(unit_raw)} (judged as {analyte['primary_unit']})"
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


# ---------------------------------------------------------------------------
# Derived lipids
# ---------------------------------------------------------------------------

# (the fraction that can be worked out, (the two operands, in the order the
# subtraction is written)). The identities are exact, so the only reason a
# derived value is second-class is provenance — which is why it is labelled.
_LIPID_IDENTITY: list[tuple[str, tuple[str, str]]] = [
    ("non_hdl", ("total_cholesterol", "hdl")),
    ("hdl", ("total_cholesterol", "non_hdl")),
]

_LIPID_LABELS = {
    "total_cholesterol": "total cholesterol",
    "hdl": "HDL cholesterol",
    "non_hdl": "non-HDL cholesterol",
}


def _operand(printed: list[dict[str, Any]], key: str, unit: str) -> dict[str, Any] | None:
    """The first printed value for ``key``, restated in ``unit``.

    ``None`` when the fraction was not printed at all or its unit cannot be
    mapped onto the target unit — a value that cannot be converted is never
    subtracted as if it were already the target's unit.
    """
    for entry in printed:
        if entry["key"] != key:
            continue
        try:
            number = float(entry["value"])
        except (TypeError, ValueError, KeyError):
            continue
        converted = to_primary_unit(key, number, str(entry.get("unit") or "").lower() or None)
        if converted is not None:
            return {"entry": entry, "converted": converted}
    return None


def _derivation_text(key: str, operands: list[dict[str, Any]], value: float, unit: str) -> str:
    """The arithmetic, spelled out in the unit the result is stated in.

    Both operands are shown in the result's unit — a difference is only
    arithmetically true in one unit — and the printed spelling is added when the
    report wrote them in another ("printed as 5.5 mmol/L, 1.3 mmol/L"), so the
    line can be checked against the report rather than taken on trust.
    """
    left, right = operands
    spelled = [f"{operand['entry']['value_text']} {operand['entry']['unit']}" for operand in operands]
    text = (
        f"{_LIPID_LABELS[left['entry']['key']]} {left['converted']:g} {unit} - "
        f"{_LIPID_LABELS[right['entry']['key']]} {right['converted']:g} {unit} = {value:g} {unit}"
    )
    if any(str(operand["entry"].get("unit")) != unit for operand in operands):
        text += f" (printed as {', '.join(spelled)})"
    return text


def _computed_entry(analyte: dict[str, Any], value: float, unit: str, operands: list[dict[str, Any]]) -> dict[str, Any]:
    """A derived fraction as a value of its own, carrying how it was reached."""
    band = analyte["ranges"][unit]
    status = _classify(value, False, band, bool(analyte.get("floor")))
    derivation = _derivation_text(analyte["key"], operands, value, unit)
    entry: dict[str, Any] = {
        "key": analyte["key"],
        "name": analyte["label"],
        "value": value,
        "value_text": f"{value:g}",
        "unit": unit,
        "unit_label": f"{unit} (computed)",
        "reference": _format_band(band, unit, False),
        "status": status,
        "severity": _SEVERITY[status],
        # A printed value points at the snippet that produced it; a derived one
        # points at the arithmetic, which is the whole of its provenance.
        "matched_text": derivation,
        "derivation": derivation,
        "computed": True,
        # The operands as they were subtracted, in the derived value's unit, so a
        # caller can redo the sum instead of trusting the result.
        "computed_from": {str(operand["entry"]["key"]): round(float(operand["converted"]), 4) for operand in operands},
        "note": analyte["note"],
    }
    if status != "normal":
        entry["explanation"] = _explain(entry, band, False)
    return entry


def _derive_lipids(printed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The lipid fractions the printed pair defines, each marked as computed.

    Three rules keep this honest:

    1. **A printed value is never overruled** — a fraction the report states is
       left exactly as printed, and a derivation never feeds another derivation,
       so nothing is computed from something that was itself computed.
    2. **The result is stated in the fraction's primary unit** (mg/dL), after
       converting both operands into it, because a panel can print the pair in
       different units and a difference is only meaningful in one of them.
    3. **The result carries the printed values' rounding**, which the derivation
       line lets a clinician see and redo rather than having to trust it.
    """
    derived: list[dict[str, Any]] = []
    printed_keys = {entry["key"] for entry in printed}
    for key, operand_keys in _LIPID_IDENTITY:
        analyte = _ANALYTE_BY_KEY[key]
        if key in printed_keys:
            continue
        unit = analyte["primary_unit"]
        operands = [_operand(printed, operand_key, unit) for operand_key in operand_keys]
        if any(operand is None for operand in operands):
            continue
        resolved = [operand for operand in operands if operand is not None]
        value = round(resolved[0]["converted"] - resolved[1]["converted"], 2)
        if value <= 0:
            # A total below its own constituent is an internally inconsistent
            # panel (a mistyped digit, or two different draws); a negative or zero
            # fraction is a claim nothing in the report supports.
            continue
        derived.append(_computed_entry(analyte, value, unit, resolved))
    return derived


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

    # After every printed value is in hand, so a derivation reads the printed
    # panel and never another derivation's output.
    values.extend(_derive_lipids(values))

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


# ---------------------------------------------------------------------------
# Measures the risk scores need (agents/risk_scores_agent)
# ---------------------------------------------------------------------------

# Assay ceilings in the unit the score compares against (ng/mL), taken from the
# same analyte table the screening flags use — the ceiling must not drift from
# the reference range the clinician sees.
_TROPONIN_CEILING = {"troponin_i": 0.04, "troponin_t": 0.01}

_HEART_RATE_RE = re.compile(
    r"\b(?:hr|heart\s+rate|pulse(?:\s+rate)?)\s*(?:is|of|was|:|=)?\s*(\d{2,3})\b",
    re.I,
)
_BP_RE = re.compile(
    r"\b(?:bp|blood\s+pressure|systolic)\s*(?:is|of|was|:|=)?\s*(\d{2,3})\s*(?:/|over)\s*(\d{2,3})\b",
    re.I,
)
_KILLIP_RE = re.compile(
    r"\bkillip(?:\s+class)?\s*(?:is|:|=)?\s*(iv|iii|ii|i|4|3|2|1)\b",
    re.I,
)
_KILLIP_ROMAN = {"1": "I", "2": "II", "3": "III", "4": "IV"}


def troponin_ratio(text: str) -> dict[str, Any] | None:
    """Troponin as a multiple of its assay ceiling, for the HEART score's item.

    HEART scores the troponin item against *that assay's* discriminative
    threshold, so this returns the ratio (value ÷ ceiling) rather than a raw
    concentration, converting ng/L to ng/mL first. A troponin reported only as
    "positive" has no ratio to give: the caller is told the number is missing
    instead of being handed a made-up one.
    """
    result = screen_report_text(text)
    for value in result.get("values", []):
        key = str(value.get("key", ""))
        ceiling = _TROPONIN_CEILING.get(key)
        if ceiling is None:
            continue
        try:
            number = float(value["value"])
        except (TypeError, ValueError, KeyError):
            continue
        unit = str(value.get("unit") or "").lower()
        if unit == "ng/l":
            number = number / 1000.0
            unit = "ng/ml"
        if unit != "ng/ml":
            continue
        return {
            "key": key,
            "value": number,
            "unit": unit,
            "ceiling": ceiling,
            "ratio": round(number / ceiling, 3),
        }
    for flag in result.get("text_flags", []):
        text = f"{flag.get('name', '')} {flag.get('explanation', '')}".lower()
        if "troponin" in text and "positive" in text:
            # A positive qualitative troponin carries no number to score.
            return {"key": "troponin_positive", "value": None, "unit": None, "ceiling": None, "ratio": None}
    return None


def vitals_from_text(text: str) -> dict[str, Any]:
    """Heart rate, blood pressure and Killip class as stated in the text.

    The risk scores need admission vitals; nothing in this system captured them
    before, so they are read from the same clinical text the labs come from
    ("BP 90/60, HR 110") and can be overridden by explicit values. Values outside
    a physiologically possible range are ignored rather than scored, and the
    diastolic must be below the systolic for a blood pressure to count.
    """
    raw = str(text or "")
    vitals: dict[str, Any] = {
        "heart_rate": None, "systolic_bp": None, "diastolic_bp": None, "killip": None,
    }

    match = _HEART_RATE_RE.search(raw)
    if match:
        value = int(match.group(1))
        if 20 <= value <= 300:
            vitals["heart_rate"] = value

    match = _BP_RE.search(raw)
    if match:
        systolic, diastolic = int(match.group(1)), int(match.group(2))
        if 40 <= systolic <= 300 and 20 <= diastolic <= 200 and diastolic < systolic:
            vitals["systolic_bp"] = systolic
            vitals["diastolic_bp"] = diastolic

    match = _KILLIP_RE.search(raw)
    if match:
        token = match.group(1).upper()
        vitals["killip"] = _KILLIP_ROMAN.get(token, token)

    return vitals


# The flat {analyte: number} view has no room for a unit, so the gates and the
# scores are written in each analyte's primary unit and the parsed value is
# CONVERTED into it rather than relabelled: a cholesterol of 5.5 handed to a
# reader that expects mg/dL is a different number, not a different label.
# Factors are the published ones — cholesterol x38.67, triglycerides x88.57,
# glucose x18.0, creatinine ÷88.4, and HbA1c's IFCC->DCCT offset formula.
_UNIT_FACTORS: dict[str, dict[tuple[str, str], float]] = {
    "total_cholesterol": {("mmol/l", "mg/dl"): 38.67},
    "ldl": {("mmol/l", "mg/dl"): 38.67},
    "hdl": {("mmol/l", "mg/dl"): 38.67},
    "triglycerides": {("mmol/l", "mg/dl"): 88.57},
    "non_hdl": {("mmol/l", "mg/dl"): 38.67},
    "glucose": {("mmol/l", "mg/dl"): 18.0},
    "creatinine": {("umol/l", "mg/dl"): 1 / 88.4},
    "troponin_i": {("ng/l", "ng/ml"): 0.001},
    "troponin_t": {("ng/l", "ng/ml"): 0.001},
    "potassium": {("meq/l", "mmol/l"): 1.0},
    "sodium": {("meq/l", "mmol/l"): 1.0},
    "egfr": {("ml/min", "ml/min/1.73m2"): 1.0},
}
_PRIMARY_UNIT = {analyte["key"]: analyte["primary_unit"] for analyte in _ANALYTES}
_HBA1C_IFCC_TO_DCCT = 10.929


def to_primary_unit(key: str, value: float, unit: str | None) -> float | None:
    """``value`` restated in the analyte's primary unit, or ``None`` when the
    printed unit cannot be mapped onto it.

    Public because the risk-score context parses the same text and must convert
    exactly as :func:`labs_for_review` does — two conversion tables would drift
    and score the same patient two different ways.
    """
    primary = _PRIMARY_UNIT.get(key)
    if primary is None or not unit or unit == primary:
        return value
    if key == "hba1c" and unit == "mmol/mol" and primary == "%":
        return round(value / _HBA1C_IFCC_TO_DCCT + 2.15, 2)
    factor = _UNIT_FACTORS.get(key, {}).get((unit, primary))
    if factor is None:
        return None
    return round(value * factor, 4)


def labs_for_review(text: str, extra: dict[str, Any] | None = None) -> dict[str, float]:
    """Numeric findings flattened for the medication safety gates.

    Reuses :func:`screen_report_text` so the numbers stay unit-aware, then
    converts each one into its analyte's primary unit and flattens it into the
    ``{analyte: number}`` shape the pharmacology agent expects — a mmol/L
    cholesterol and a µmol/L creatinine arrive as mg/dL, an HbA1c in mmol/mol
    as a percentage, and an ng/L troponin as ng/mL. A value whose printed unit
    has no defined conversion is left out rather than passed on in a unit the
    caller would misread, except for troponin, whose abnormal flag is carried so
    a safety gate does not silently lose it. ``extra`` is applied last, so a
    caller-supplied value wins over the parsed one and must itself be in the
    primary unit.
    """
    labs: dict[str, float] = {}
    if isinstance(text, str) and text.strip():
        for value in screen_report_text(text).get("values", []):
            key = str(value.get("key", ""))
            try:
                number = float(value["value"])
            except (TypeError, ValueError, KeyError):
                continue
            unit = str(value.get("unit") or "").lower() or None
            converted = to_primary_unit(key, number, unit)
            if converted is None:
                if key in ("troponin_i", "troponin_t") and value.get("severity") in ("critical", "abnormal"):
                    labs["troponin_flag"] = 1.0
                continue
            number = converted
            unit = _PRIMARY_UNIT.get(key) or unit
            if key in ("troponin_i", "troponin_t"):
                if unit == "ng/ml":
                    labs["troponin"] = number
                elif value.get("severity") in ("critical", "abnormal"):
                    labs["troponin_flag"] = 1.0
                continue
            labs[key] = number
    for key, raw in (extra or {}).items():
        try:
            labs[str(key)] = float(raw)
        except (TypeError, ValueError):
            continue
    return labs
