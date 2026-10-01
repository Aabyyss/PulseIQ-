"""Evaluation harness tests (Area 7 of the review).

WER math, extraction precision/recall against the labelled dataset,
SUS scoring, and the benchmark report shape.
"""

import pytest

from backend.evaluation import (
    EXTRACTION_DATASET,
    corpus_wer,
    extraction_metrics,
    format_report,
    run_benchmark,
    sus_score,
    word_error_rate,
)


# --- WER ------------------------------------------------------------------

def test_wer_perfect_match_is_zero():
    assert word_error_rate("chest pain for two days", "chest pain for two days") == 0.0


def test_wer_single_substitution():
    # 1 error / 5 words
    assert word_error_rate("chest pain for two days", "chest pain for two dogs") == 0.2


def test_wer_is_case_and_punctuation_insensitive():
    assert word_error_rate("Chest pain!", "chest pain") == 0.0
    assert word_error_rate("Chest, pain.", "chest pain") == 0.0


def test_wer_empty_reference():
    assert word_error_rate("", "") == 0.0
    assert word_error_rate("", "extra words") == 1.0


def test_corpus_wer_aggregates_errors_not_means():
    result = corpus_wer([
        ("one two three four", "one two three four"),   # 0/4
        ("one two", "one"),                             # 1/2
    ])
    # total errors 1 / total words 6
    assert result["wer"] == pytest.approx(1 / 6, abs=1e-4)
    assert result["total_reference_words"] == 6
    assert result["utterances"] == 2


# --- extraction P/R/F1 -----------------------------------------------------

def test_extraction_metrics_against_labelled_dataset():
    metrics = extraction_metrics()
    assert set(metrics) >= {"precision", "recall", "f1", "cases", "exact_match_rate"}
    assert 0.0 <= metrics["precision"] <= 1.0
    assert 0.0 <= metrics["recall"] <= 1.0
    assert metrics["cases"] == len(EXTRACTION_DATASET)
    # The extractor is rule-based on well-covered concepts; it should be
    # strong. Floor the assertion so legitimate dictionary tweaks don't
    # silently tank quality unnoticed.
    assert metrics["f1"] >= 0.75, metrics["failures"]


def test_extraction_negation_cases_produce_no_false_positives():
    from agents.nlp_symptom_agent import extract_symptoms_from_text
    negation_cases = [c for c in EXTRACTION_DATASET if not c["expected"]]
    assert negation_cases, "dataset should contain negation controls"
    for case in negation_cases:
        predicted = set(extract_symptoms_from_text(case["text"]))
        assert predicted == set(), (case, predicted)


def test_extraction_dataset_is_auditable():
    # Every labelled case records who labelled it.
    assert all(case.get("source") for case in EXTRACTION_DATASET)


# --- SUS -------------------------------------------------------------------

def test_sus_all_fives_is_50():
    # Agreeing with the NEGATIVE items too cancels the positive ones —
    # standard SUS lands all-5s at exactly the neutral midpoint.
    assert sus_score([5] * 10)["score"] == 50.0


def test_sus_all_threes_is_50():
    assert sus_score([3] * 10)["score"] == 50.0


def test_sus_polarity_is_applied_per_item():
    # Positive-on-odd/negative-on-even at max disagreement → 100;
    # the exact inverse → 0. This proves the odd/even polarity flip.
    assert sus_score([5, 1, 5, 1, 5, 1, 5, 1, 5, 1])["score"] == 100.0
    assert sus_score([1, 5, 1, 5, 1, 5, 1, 5, 1, 5])["score"] == 0.0


def test_sus_rejects_wrong_length_and_range():
    with pytest.raises(ValueError):
        sus_score([3, 3, 3])
    with pytest.raises(ValueError):
        sus_score([0] * 10)


def test_sus_grades_and_interpretation():
    # Perfect polarity: love the positives, reject the negatives.
    result = sus_score([5, 1, 5, 1, 5, 1, 5, 1, 5, 1])
    assert result["grade"] == "A"
    assert "above average" in result["interpretation"]
    below = sus_score([1, 5, 1, 5, 1, 5, 1, 5, 1, 5])
    assert below["score"] == 0.0
    assert below["grade"] == "F"


# --- benchmark report -------------------------------------------------------

def test_run_benchmark_shape():
    results = run_benchmark()
    assert "extraction" in results and "wer" in results
    assert 0.0 <= results["wer"]["wer"] <= 1.0


def test_format_report_is_markdown_with_numbers():
    report = format_report(run_benchmark())
    assert report.startswith("### PulseIQ offline benchmark")
    assert "precision" in report and "WER" in report
