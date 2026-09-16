import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.feature_mapper_agent import map_symptoms_to_features
from agents.explainability_agent import explain_prediction


# Example symptoms
symptoms = ["chest pain", "shortness of breath"]

# Convert symptoms to model features
features = map_symptoms_to_features(symptoms)

# Generate explanation
explanation = explain_prediction(features)

print("Top contributing factors:")
print(explanation)