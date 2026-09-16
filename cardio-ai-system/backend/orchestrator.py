import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.nlp_symptom_agent import extract_symptoms_from_text
from agents.feature_mapper_agent import map_symptoms_to_features
from agents.prediction_agent import predict_heart_disease


def risk_from_probability(probability: float) -> str:
    """Shared risk-band mapping, calibrated to the retrained model's probabilities."""
    if probability > 0.75:
        return "High"
    if probability > 0.45:
        return "Medium"
    return "Low"


def run_diagnosis_from_text(text):

    symptoms = extract_symptoms_from_text(text)

    features = map_symptoms_to_features(symptoms)

    prediction, probability = predict_heart_disease(features)

    risk = risk_from_probability(float(probability))

    return {
        "text": text,
        "symptoms": symptoms,
        "features": features,
        "prediction": int(prediction),
        "probability": float(probability),
        "risk_level": risk
    }