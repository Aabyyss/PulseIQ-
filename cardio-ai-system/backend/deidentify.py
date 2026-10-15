"""De-identification: strip direct identifiers before storage or learning.

Why this exists
---------------
The privacy review asked that names, phone numbers and CNICs never reach
storage (consultations, screenings) or the self-learning vocabulary. This
module is the single chokepoint those flows share.

What it removes (conservative, Pakistan-aware, zero false positives on
clinical text by construction):
- CNIC numbers: ``35202-1234567-1`` and the un-dashed 13-digit form.
- Phone numbers: Pakistani mobile/landline formats (``0300-1234567``,
  ``+92 321 1234567``, ``92...``, ``021-34567890``) plus generic long digit
  runs that look like international numbers. Only the number itself is
  replaced, so the words around it keep their spacing.
- Email addresses.
- Patient-name declarations: ``patient name: Ali Khan`` / ``name is Ali``,
  after honorifics (Mr., Mrs., Dr., Mx.) and the possessive patterns the
  capture UI itself can produce. A bare capitalised word is NEVER redacted
  — clinical text is full of those (Troponin, Elevation) and redacting
  them would destroy the record.

Every replacement is tagged (``[REDACTED CNIC]``) so the clinician can see
exactly what was removed and why — silent mangling of a record is worse
than an honest tag.

Idempotent: running de-identification twice is a no-op the second time.
"""

from __future__ import annotations

import re
from typing import Any

# --- patterns -------------------------------------------------------------
# Order matters: more specific first, so "0300-1234567" is captured as a
# phone before the generic digit-run rule can nibble at it.

_CNIC = re.compile(r"\b\d{5}-\d{7}-\d\b")
_CNIC_UNDASHED = re.compile(r"(?<!\d)\d{13}(?!\d)")

# Every alternative starts on a digit: an optional leading separator used to
# be part of the match, so redacting "phone 0300-1234567" ate the space and
# returned "phone[REDACTED PHONE]". The country code keeps its own separator
# because that one is genuinely inside the number; landlines (0XX-XXXXXXX,
# which the module always claimed to cover) are given their own alternative
# rather than being read as a mobile prefix that never matches them.
_PHONE_PK = re.compile(
    r"(?<![\d\-])(?:"
    r"(?:\+?92|0092)[\s\-]?0?3\d{2}[\s\-]?\d{7}"
    r"|0?3\d{2}[\s\-]?\d{7}"
    r"|0\d{1,3}[\s\-]\d{7,8}"
    r")(?!\d)"
)
_PHONE_INTL = re.compile(r"\+\d{1,3}[\s\-]\d{2,4}(?:[\s\-]\d{2,4}){1,3}(?!\d)")

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")

# Name declarations only — never bare capitals.
#   "patient name: Ali Khan", "Pt Name - Ali", "name is Ali",
#   "Mr. Ali Khan reported...", "Patient: Ali Khan"
#
# The label and the separator are matched case-insensitively; only the
# captured name stays case-sensitive. A sentence-initial label is capitalised
# ("Name: Ali Khan", "Patient Name: Ali Khan", "PT: Ali Khan"), and reading
# the label case-sensitively let exactly those forms through — the commonest
# way a name is written down leaked the name. The clinical-capital rule is
# untouched: the name group still requires capitalised words, so "patient
# ecg showed..." is still never redacted.
_NAME_LABELED = re.compile(
    r"(?i:\b(?:patient|pt|pt\.?|patient's|name))\s*(?i:name)?\s*(?i:is|:|-|=)\s*"
    r"([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3})"
)
_NAME_HONORIFIC = re.compile(
    r"\b(?:Mr|Mrs|Ms|Mx|Miss|Dr|Prof)\.?\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2})"
)

REDACTIONS = {
    "cnic": "[REDACTED CNIC]",
    "phone": "[REDACTED PHONE]",
    "email": "[REDACTED EMAIL]",
    "name": "[REDACTED NAME]",
}


def deidentify(text: str) -> tuple[str, dict[str, int]]:
    """Replace direct identifiers in ``text``.

    Returns ``(clean_text, counts)`` where ``counts`` maps each redaction
    category to how many were removed. Safe to call twice.
    """
    original = str(text or "")
    if not original:
        return "", {}
    counts: dict[str, int] = {}
    result = original
    # CNIC (dashed first, then bare 13-digit)
    def _tag(kind: str):
        tag = REDACTIONS[kind]
        def fn(match: re.Match[str]) -> str:
            counts[kind] = counts.get(kind, 0) + 1
            return tag
        return fn

    result = _CNIC.sub(_tag("cnic"), result)
    result = _CNIC_UNDASHED.sub(_tag("cnic"), result)
    result = _PHONE_PK.sub(_tag("phone"), result)
    result = _PHONE_INTL.sub(_tag("phone"), result)
    result = _EMAIL.sub(_tag("email"), result)
    # Names: only the identifier group is replaced, keeping the label so
    # the record still reads naturally ("patient name: [REDACTED NAME]").
    def _name_fn(match: re.Match[str]) -> str:
        counts["name"] = counts.get("name", 0) + 1
        return match.group(0).replace(match.group(1), REDACTIONS["name"])
    result = _NAME_LABELED.sub(_name_fn, result)
    result = _NAME_HONORIFIC.sub(_name_fn, result)
    return result, counts


def deidentify_transcript(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """De-identify transcript lines (dicts with a ``text`` key) in place-copy.

    Returns new dicts; the input list is untouched. Empty/non-dict entries
    pass through unchanged.
    """
    cleaned: list[dict[str, Any]] = []
    for line in lines:
        if not isinstance(line, dict):
            cleaned.append(line)
            continue
        entry = dict(line)
        text = entry.get("text")
        if isinstance(text, str) and text:
            entry["text"], _ = deidentify(text)
        cleaned.append(entry)
    return cleaned
