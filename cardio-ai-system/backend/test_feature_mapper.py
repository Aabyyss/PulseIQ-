"""Feature-mapper checks: symptoms must shift model features coherently.

Run directly (matching the CI style):
    python backend/test_feature_mapper.py
"""

import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.feature_mapper_agent import map_symptoms_to_features

FEATURE_NAMES = [
    "age", "sex", "cp", "trestbps", "chol", "fbs",
    "restecg", "thalach", "exang", "oldpeak",
    "slope", "ca", "thal",
]

KEY_FIELDS = ("age", "cp", "trestbps", "thalach", "oldpeak", "ca", "thal")


def features_for(symptoms):
    return dict(zip(FEATURE_NAMES, map_symptoms_to_features(symptoms)))


CASES = [
    ([], lambda f: f["cp"] == 3 and f["thalach"] == 165,
     "baseline stays asymptomatic with good capacity"),
    (["chest pain"], lambda f: f["cp"] == 0 and f["exang"] == 1 and f["oldpeak"] >= 1.8,
     "chest pain maps to the typical-angina cluster"),
    (["cough"], lambda f: f["cp"] == 3 and f["thalach"] <= 145,
     "isolated cough shifts mildly and keeps chest features clean"),
    (["sweating"], lambda f: f["trestbps"] >= 140 and f["oldpeak"] >= 1.2,
     "sweating shifts toward the ischemic profile"),
    (["nausea"], lambda f: f["age"] >= 54 and f["cp"] == 3,
     "nausea alone adjusts the atypical profile without chest features"),
    (["leg swelling"], lambda f: f["thalach"] <= 125 and f["oldpeak"] >= 1.6 and f["ca"] >= 2,
     "leg edema shifts toward congestion/vessel involvement"),
    (["leg swelling", "shortness of breath"], lambda f: f["thalach"] <= 118 and f["ca"] >= 2,
     "heart-failure cluster keeps the strongest SOB values"),
]


def main() -> int:
    failures = 0
    for symptoms, check, label in CASES:
        features = features_for(symptoms)
        ok = check(features)
        print(f"[{'PASS' if ok else 'FAIL'}] {label} :: {symptoms}")
        if not ok:
            failures += 1
            print("   features:", {k: features[k] for k in KEY_FIELDS})

    if failures:
        print(f"{failures} feature-mapper case(s) failed")
        return 1
    print("All feature-mapper cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())