import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.nlp_symptom_agent import extract_symptoms_from_text
from agents.feature_mapper_agent import map_symptoms_to_features
from agents.prediction_agent import predict_heart_disease
from agents.pharmacology_agent import review_medications


def risk_from_probability(probability: float) -> str:
    """Shared risk-band mapping, calibrated to the retrained model's probabilities."""
    if probability > 0.75:
        return "High"
    if probability > 0.45:
        return "Medium"
    return "Low"


def run_medication_review(text="", patient=None, symptoms=None, report_text=""):
    """Medication options and safety review for one encounter.

    ``patient`` carries what the clinician already knows: ``age``, ``sex``,
    ``conditions``, ``allergies``, ``current_medications``, ``labs`` (numeric
    findings, e.g. from ``lab_report``) and optionally ``pregnancy``. The API
    layer owns entity/lab extraction and fills those fields; this function
    owns symptom extraction and the risk band, so every medication review is
    banded exactly like ``/diagnose`` (single source of truth).

    Nothing here is stored, and nothing is assumed: facts that were not
    supplied come back in ``missing_information``.
    """
    context = dict(patient or {})
    narrative = f"{text or ''}\n{report_text or ''}".strip()

    if symptoms is None:
        symptoms = extract_symptoms_from_text(narrative)

    diagnosis = run_diagnosis_from_text(narrative, symptoms=symptoms) if narrative else None

    risk = context.get("risk_level")
    if risk not in ("Low", "Medium", "High"):
        risk = diagnosis["risk_level"] if diagnosis else None

    medications = review_medications(
        symptoms=symptoms,
        conditions=context.get("conditions"),
        allergies=context.get("allergies"),
        current_medications=context.get("current_medications"),
        age=context.get("age"),
        sex=context.get("sex"),
        risk_level=risk,
        labs=context.get("labs"),
        pregnancy=context.get("pregnancy"),
    )

    return {"symptoms": symptoms, "diagnosis": diagnosis, "medications": medications}


def run_diagnosis_from_text(text, symptoms=None):
    """Screen a narrative. ``symptoms`` may carry pre-extracted findings
    (e.g. merged with a clinician's learned vocabulary by realtime_service)
    so the risk estimate reflects what the caller already knows."""

    if symptoms is None:
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