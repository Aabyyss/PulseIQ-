import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.feature_mapper_agent import map_symptoms_to_features

symptoms = ["chest pain", "shortness of breath"]

features = map_symptoms_to_features(symptoms)

print("Generated Features:", features)