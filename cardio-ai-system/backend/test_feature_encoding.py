"""The mapper's values must exist in the dataset's codebook.

Replacing the Kaggle copy with the UCI original changed the categorical
encodings: `cp` is 1–4 (not 0–3), `thal` is 3/6/7 (not 1–3), `slope` is 1–3 with
1 = upsloping. The mapper still emitted the old shift, so a classic
acute-coronary presentation (`cp=0`, `thal=2`) became values the forest had
never seen and "crushing chest pain with sweating and left-arm pain" scored
Low.

These tests pin the contract between the codebook, the mapper and the model:
every emitted value is one the dataset actually contains, and the canonical
presentations land in the band a clinician would expect.
"""

import itertools
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from agents.feature_mapper_agent import map_symptoms_to_features  # noqa: E402
from agents.prediction_agent import feature_names, predict_heart_disease  # noqa: E402
from backend.orchestrator import risk_from_probability  # noqa: E402
from backend.train_model import DATA_PATH, load_dataset  # noqa: E402

SYMPTOMS = [
    "chest pain",
    "shortness of breath",
    "dizziness",
    "fatigue",
    "palpitations",
    "nausea",
    "sweating",
    "leg swelling",
    "cough",
    "exercise pain",
    "radiating pain",
]

# UCI `heart-disease.names`. Values outside these sets cannot be produced by the
# source data, so the model cannot have learned anything about them.
CODEBOOK = {
    "sex": {0, 1},
    "cp": {1, 2, 3, 4},
    "fbs": {0, 1},
    "restecg": {0, 1, 2},
    "exang": {0, 1},
    "slope": {1, 2, 3},
    "ca": {0, 1, 2, 3},
    "thal": {3, 6, 7},
}

# Plausible physiological ranges for the continuous fields, so a typo (age 5,
# heart rate 900) fails here rather than being absorbed by the forest.
RANGES = {
    "age": (18, 100),
    "trestbps": (80, 220),
    "chol": (100, 500),
    "thalach": (60, 210),
    "oldpeak": (0.0, 6.0),
}


def features_for(symptoms):
    return dict(zip(feature_names, map_symptoms_to_features(list(symptoms))))


def symptom_sets():
    for size in range(0, 4):
        for combination in itertools.combinations(SYMPTOMS, size):
            yield combination


def test_mapper_matches_the_model_feature_contract():
    features = map_symptoms_to_features(["chest pain"])
    assert len(features) == len(feature_names)
    assert features_for(["chest pain"]).keys() == set(feature_names)


@pytest.mark.parametrize("symptoms", list(symptom_sets()))
def test_every_emitted_value_is_in_the_codebook(symptoms):
    features = features_for(symptoms)
    for name, allowed in CODEBOOK.items():
        assert features[name] in allowed, f"{name}={features[name]} for {symptoms}"
    for name, (low, high) in RANGES.items():
        assert low <= features[name] <= high, f"{name}={features[name]} for {symptoms}"


def test_no_symptoms_bands_low():
    probability = predict_heart_disease(map_symptoms_to_features([]))[1]
    assert probability < 0.45
    assert risk_from_probability(float(probability)) == "Low"


def test_stable_chest_pain_is_at_least_medium():
    """Typical angina is disease-leaning; it must not be screened as low risk."""
    probability = predict_heart_disease(map_symptoms_to_features(["chest pain"]))[1]
    assert probability >= 0.45
    assert features_for(["chest pain"])["cp"] == 1


def test_chest_pain_with_autonomic_or_radiation_signs_bands_high():
    presentation = ["chest pain", "sweating", "radiating pain"]
    probability = predict_heart_disease(map_symptoms_to_features(presentation))[1]
    assert risk_from_probability(float(probability)) == "High"
    # And the escalation is visible in the features, not only in the score.
    features = features_for(presentation)
    assert features["slope"] == 3
    assert features["thal"] == 7
    assert features["ca"] >= 2


def test_isolated_benign_symptoms_stay_low():
    for symptoms in (["cough"], ["palpitations"], ["dizziness"]):
        probability = predict_heart_disease(map_symptoms_to_features(symptoms))[1]
        assert risk_from_probability(float(probability)) == "Low", symptoms


def test_the_codebook_matches_the_data_on_disk():
    """If the dataset is swapped again, the encodings above must be revisited."""
    _, data = load_dataset(DATA_PATH)
    for name, allowed in CODEBOOK.items():
        assert set(data[name].unique()) <= allowed, name
    # Every codebook value except 'atypical angina' (2) and 'LV hypertrophy' (2)
    # still appears, so the mapping is not describing a fiction.
    assert set(data["cp"].unique()) == {1, 2, 3, 4}
