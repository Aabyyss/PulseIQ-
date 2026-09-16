from __future__ import annotations


PAIN_POINT_MAP = {
    "chest pain": {"x": 0.0, "y": 0.1, "z": 0.35, "label": "Central chest"},
    "shortness of breath": {"x": 0.12, "y": 0.2, "z": 0.22, "label": "Upper chest/lung strain"},
    "palpitations": {"x": -0.08, "y": 0.05, "z": 0.32, "label": "Cardiac rhythm focus"},
    "dizziness": {"x": 0.0, "y": 0.35, "z": 0.15, "label": "Perfusion concern"},
    "fatigue": {"x": 0.0, "y": -0.15, "z": 0.2, "label": "Systemic fatigue pattern"},
}


def map_symptoms_to_pain_points(symptoms: list[str]) -> list[dict]:
    points = []
    for symptom in symptoms:
        mapped = PAIN_POINT_MAP.get(symptom)
        if mapped:
            points.append({"symptom": symptom, **mapped})
    return points
