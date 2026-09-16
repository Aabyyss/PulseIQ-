from __future__ import annotations


def robustness_checks(transcript: str) -> dict:
    t = transcript.lower()
    return {
        "negation_present": "no " in t or "not " in t,
        "very_short_input": len(t.split()) < 4,
        "noisy_input_warning": any(token in t for token in ["umm", "uh", "..."]),
    }
