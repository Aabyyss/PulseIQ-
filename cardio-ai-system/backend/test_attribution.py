"""Suggestion attribution & plan confidence (Areas 2+3 of the review).

Every suggestion must map to a source; low-evidence situations must say
"not enough information" instead of guessing.
"""

from agents.attribution_agent import attribute_suggestions, plan_confidence
from agents.doctor_copilot_agent import suggest_next_questions
from agents.evidence_retrieval_agent import retrieve_evidence_snippets
from agents.uncertainty_agent import estimate_prediction_uncertainty


QUESTIONS = suggest_next_questions(symptoms=["chest pain", "sweating"], transcript="chest pain with sweating")
TESTS = ["12-lead ECG", "Serial troponin", "Vital signs and pulse oximetry"]
STEPS = ["Escalate immediately if red-flag symptoms appear."]


def test_every_suggestion_gets_a_source():
    sources = attribute_suggestions(QUESTIONS, TESTS, STEPS)
    for item in QUESTIONS + TESTS + STEPS:
        assert item in sources, f"no source for: {item}"
        assert sources[item], f"empty source for: {item}"


def test_key_suggestions_cite_the_expected_guideline():
    sources = attribute_suggestions(QUESTIONS, TESTS, STEPS)
    ecg = next(s for t, s in sources.items() if "ECG" in t)
    troponin = next(s for t, s in sources.items() if "troponin" in t.lower())
    assert "ESC" in ecg or "ACC" in ecg
    assert "troponin" in troponin.lower() or "ESC" in troponin or "ACC" in troponin


def test_fallback_source_is_honest_not_fake_guideline():
    sources = attribute_suggestions(["Describe the discomfort in your own words."], [], [])
    source = sources["Describe the discomfort in your own words."]
    assert "derived from this encounter" in source
    assert "guideline —" not in source  # no fake citation


def test_confidence_low_and_insufficient_when_no_evidence():
    conf = plan_confidence(symptoms=[], report_text="", probability=0.5)
    assert conf["confidence"] == "low"
    assert conf["insufficient_information"] == "true"
    assert conf["reason"]


def test_confidence_high_only_with_corroboration():
    conf = plan_confidence(
        symptoms=["chest pain", "sweating", "shortness of breath"],
        report_text="",
        probability=0.85,
    )
    assert conf["confidence"] == "high"
    assert conf["insufficient_information"] == "false"


def test_confidence_moderate_for_few_signals():
    conf = plan_confidence(symptoms=["chest pain"], report_text="", probability=0.6)
    assert conf["confidence"] in ("low", "moderate")
    assert conf["insufficient_information"] == "false"


def test_report_text_rescues_insufficient_state():
    conf = plan_confidence(symptoms=[], report_text="troponin 0.05", probability=0.5)
    assert conf["insufficient_information"] == "false"


def test_uncertainty_agent_still_provides_score():
    u = estimate_prediction_uncertainty(probability=0.92)
    assert u["confidence_bucket"] == "high_confidence"
    assert u["confidence_score"] >= 0.7


def test_evidence_snippets_present_for_symptoms():
    snippets = retrieve_evidence_snippets(symptoms=["chest pain"], report_text="")
    assert snippets and snippets[0]["topic"] and snippets[0]["summary"]
