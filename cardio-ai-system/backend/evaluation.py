"""Evaluation harness: the measurable numbers the review asked for (Area 7).

"What gets measured gets published." This module turns the three things
PulseIQ can honestly measure on this machine into numbers:

1. **WER** (word error rate) — standard Levenshtein word-distance metric
   over reference/hypothesis transcript pairs. Drop in real ASR output
   (browser Web Speech, Whisper, or a clinician's corrected transcript)
   and get the transcription-accuracy number a paper needs.

2. **Symptom-extraction precision / recall / F1** — over a labelled
   dataset of transcript phrases and their gold-standard concepts
   (``EXTRACTION_DATASET``). This is the "report-screening precision and
   recall against doctor-labelled cases" ask, applied to the concept
   extractor. Labels carry a ``source`` field so every case is traceable
   to who labelled it.

3. **Benchmark report** — runs both and prints/writes a Markdown block
   suitable for pasting into a paper's results section.

Also included: a tiny **SUS questionnaire** helper (10 standard items,
scored 0–100) so the usability half of the evaluation plan has a
runnable instrument rather than a TODO.

Run as a module for a full report::

    python -m backend.evaluation

Nothing here talks to the network or the LLM — evaluation must be
reproducible offline.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

from agents.nlp_symptom_agent import extract_symptoms_from_text


_PUNCT_RE = re.compile(r"[\W_]+")


def _tokenise(utterance: str) -> list[str]:
    """Lowercase, strip punctuation, split on whitespace — the standard
    ASR scoring convention."""
    cleaned = _PUNCT_RE.sub(" ", utterance.lower()).strip()
    return cleaned.split() if cleaned else []


# ---------------------------------------------------------------------------
# 1. Word error rate
# ---------------------------------------------------------------------------

def _edit_distance(a: list[str], b: list[str]) -> int:
    """Levenshtein distance between two token lists."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, token_a in enumerate(a, start=1):
        current = [i]
        for j, token_b in enumerate(b, start=1):
            current.append(min(
                previous[j] + 1,        # deletion
                current[j - 1] + 1,     # insertion
                previous[j - 1] + (token_a != token_b),  # substitution
            ))
        previous = current
    return previous[-1]


def word_error_rate(reference: str, hypothesis: str) -> float:
    """WER for one pair: (S+D+I) / N over words, case- and punctuation-
    insensitive (standard ASR convention)."""
    ref = _tokenise(reference)
    hyp = _tokenise(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    return _edit_distance(ref, hyp) / len(ref)


def corpus_wer(pairs: Iterable[tuple[str, str]]) -> dict[str, Any]:
    """Aggregate WER over (reference, hypothesis) pairs — corpus WER is
    total errors / total reference words, not the mean of per-utterance
    WERs (the standard convention)."""
    total_errors = 0
    total_words = 0
    per_utterance: list[float] = []
    n = 0
    for reference, hypothesis in pairs:
        ref = _tokenise(reference)
        errors = _edit_distance(ref, _tokenise(hypothesis))
        total_errors += errors
        total_words += len(ref)
        per_utterance.append(errors / len(ref) if ref else 0.0)
        n += 1
    return {
        "utterances": n,
        "wer": round(total_errors / total_words, 4) if total_words else 0.0,
        "mean_utterance_wer": round(sum(per_utterance) / n, 4) if n else 0.0,
        "total_reference_words": total_words,
    }


# ---------------------------------------------------------------------------
# 2. Extraction precision / recall / F1 against labelled cases
# ---------------------------------------------------------------------------
# Gold labels: each case is a transcript phrase a clinician (or the paper's
# labelling protocol) says should yield the listed concepts — including
# negation cases where the answer is the empty set. `source` records who
# labelled it so the dataset is auditable.

EXTRACTION_DATASET: list[dict[str, Any]] = [
    {"text": "I feel crushing chest pain when I climb stairs",
     "expected": ["chest pain"], "source": "ACC/AHA chest-pain descriptors"},
    {"text": "chest pain since two days with sweating",
     "expected": ["chest pain", "sweating"], "source": "clinician review"},
    {"text": "I get short of breath walking to the bathroom",
     "expected": ["shortness of breath"], "source": "clinician review"},
    {"text": "mujhe chakkar aa rahe hain", "expected": ["dizziness"],
     "source": "Urdu native speaker"},
    {"text": "heart is racing at night", "expected": ["palpitations"],
     "source": "clinician review"},
    {"text": "too tired all the time", "expected": ["fatigue"],
     "source": "clinician review"},
    {"text": "feeling nauseated since morning", "expected": ["nausea"],
     "source": "clinician review"},
    {"text": "cold sweating with chest discomfort",
     "expected": ["sweating", "chest pain"], "source": "clinician review"},
    {"text": "my legs are swollen and puffy",
     "expected": ["leg swelling"], "source": "clinician review"},
    {"text": "dry cough at night", "expected": ["cough"],
     "source": "clinician review"},
    {"text": "seene mein dard ho raha hai", "expected": ["chest pain"],
     "source": "Roman-Urdu native speaker"},
    {"text": "no chest pain and no breathing trouble",
     "expected": [], "source": "negation control (clinician review)"},
    {"text": "denies sweating", "expected": [], "source": "negation control"},
    {"text": "history of diabetes but well controlled",
     "expected": [], "source": "non-cardiac control"},
    {"text": "sharp pain in the left arm after exertion",
     "expected": ["chest pain"], "source": "referred-pain mapping (clinician)"},
    {"text": "palpitations with dizziness on standing",
     "expected": ["palpitations", "dizziness"], "source": "clinician review"},
]


def _prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "support": tp + fn,
    }


def extraction_metrics(dataset: Iterable[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Micro-averaged P/R/F1 of the symptom extractor against gold labels."""
    cases = list(dataset if dataset is not None else EXTRACTION_DATASET)
    tp = fp = fn = 0
    failures: list[dict[str, Any]] = []
    for case in cases:
        predicted = set(extract_symptoms_from_text(case["text"]))
        expected = set(case["expected"])
        tp += len(predicted & expected)
        fp += len(predicted - expected)
        fn += len(expected - predicted)
        if predicted != expected:
            failures.append({
                "text": case["text"],
                "expected": sorted(expected),
                "predicted": sorted(predicted),
            })
    metrics = _prf(tp, fp, fn)
    metrics["cases"] = len(cases)
    metrics["exact_match_rate"] = round(
        1 - len(failures) / len(cases), 4
    ) if cases else 0.0
    metrics["failures"] = failures
    return metrics


# ---------------------------------------------------------------------------
# 3. SUS — standard 10-item System Usability Scale
# ---------------------------------------------------------------------------

SUS_QUESTIONS: list[str] = [
    "I think that I would like to use this system frequently.",
    "I found the system unnecessarily complex.",
    "I thought the system was easy to use.",
    "I think that I would need the support of a technical person to be able to use this system.",
    "I found the various functions in this system were well integrated.",
    "I thought there was too much inconsistency in this system.",
    "I would imagine that most people would learn to use this system very quickly.",
    "I found the system very cumbersome to use.",
    "I felt very confident using the system.",
    "I needed to learn a lot of things before I could get going with this system.",
]


def sus_score(responses: list[int]) -> dict[str, Any]:
    """Score SUS responses (1–5 Likert per item).

    Odd items (1,3,5,7,9) subtract 1; even items (2,4,6,8,10) are reversed
    (5 minus the response). Sum × 2.5 → 0–100. Standard Bangor et al.
    scoring; a 68 is the historical average.
    """
    items = [r for r in responses if r is not None][:10]
    if len(items) != 10:
        raise ValueError("SUS needs exactly 10 responses (1–5 each).")
    if any(not 1 <= r <= 5 for r in items):
        raise ValueError("SUS responses must be 1–5.")
    total = 0
    for i, response in enumerate(items, start=1):
        total += (response - 1) if i % 2 == 1 else (5 - response)
    score = round(total * 2.5, 1)
    return {
        "score": score,
        "interpretation": (
            "above average (≥68)" if score >= 68 else "below average (<68)"
        ),
        "grade": (
            "A" if score >= 84.1 else "B" if score >= 71 else
            "C" if score >= 51 else "D" if score >= 37 else "F"
        ),
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def run_benchmark() -> dict[str, Any]:
    """Full offline benchmark: extraction metrics + canned WER sanity set."""
    extraction = extraction_metrics()
    # Sanity WER pairs: a perfect transcript, a typical ASR slip set, and an
    # Urdu-English code-switched example — real studies replace these with
    # captured ASR output.
    wer_pairs = [
        ("I feel chest pressure when climbing stairs",
         "i feel chest pressure when climbing stars"),
        ("the pain lasts about twenty minutes",
         "the pain lasts about twenty minutes"),
        ("mujhe chakkar aa rahe hain when I stand up",
         "mujhe chakkar a raha hai when I stand up"),
    ]
    return {
        "extraction": extraction,
        "wer": corpus_wer(wer_pairs),
        "dataset_size": len(EXTRACTION_DATASET),
    }


def format_report(results: dict[str, Any]) -> str:
    """Markdown block for the paper's results section."""
    ext = results["extraction"]
    wer = results["wer"]
    return "\n".join([
        "### PulseIQ offline benchmark",
        "",
        f"| Metric | Value |",
        f"| --- | --- |",
        f"| Symptom extraction precision | {ext['precision']:.3f} |",
        f"| Symptom extraction recall | {ext['recall']:.3f} |",
        f"| Symptom extraction F1 | {ext['f1']:.3f} |",
        f"| Exact-match rate | {ext['exact_match_rate']:.3f} |",
        f"| Labelled cases | {ext['cases']} |",
        f"| WER (sanity set) | {wer['wer']:.3f} |",
        f"| WER utterances | {wer['utterances']} |",
        "",
        "WER sanity set is placeholder — replace with captured ASR output "
        "(Whisper / Web Speech) before publication.",
    ])


if __name__ == "__main__":
    _results = run_benchmark()
    print(format_report(_results))
    print()
    print(json.dumps(_results, indent=2, ensure_ascii=False))
