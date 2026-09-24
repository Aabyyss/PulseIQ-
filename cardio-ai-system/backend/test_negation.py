"""Negation-aware symptom extraction tests.

Run directly (matching the CI style):
    python backend/test_negation.py
"""

import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.nlp_symptom_agent import extract_symptoms_from_text

CASES = [
    # (narrative, expected positive concepts)
    ("I feel chest pressure and breathing difficulty when walking upstairs",
     {"chest pain", "shortness of breath"}),
    ("no chest pain on exertion", set()),
    ("denies chest pain and shortness of breath", set()),
    ("no chest pain, no palpitations", set()),
    ("patient has no chest pain but does have palpitations", {"palpitations"}),
    ("ruled out shortness of breath; reports dizziness", {"dizziness"}),
    ("resolved chest tightness, new episode of faint", {"dizziness"}),
    ("crushing chest pain radiating to left arm", {"chest pain"}),
    ("Denies chest pain. Reports an episode of faint last week.", {"dizziness"}),
    ("", set()),
]


def main() -> int:
    failures = 0
    for text, expected in CASES:
        got = set(extract_symptoms_from_text(text))
        if got != expected:
            failures += 1
            print(f"FAIL: {text!r} -> {sorted(got)}, expected {sorted(expected)}")

    # Details mode: matched surface phrases returned for transparency.
    symptoms, details = extract_symptoms_from_text(
        "no chest pain, yes dizziness", return_details=True
    )
    if symptoms != ["dizziness"] or details != {"dizziness": "dizziness"}:
        failures += 1
        print(f"FAIL: details mode -> {symptoms}, {details}")

    if failures:
        print(f"{failures} negation test(s) failed")
        return 1
    print("All negation tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
