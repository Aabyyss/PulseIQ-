import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.feature_mapper_agent import map_symptoms_to_features
from agents.prediction_agent import predict_heart_disease

symptoms = ["chest pain", "shortness of breath"]

features = map_symptoms_to_features(symptoms)

prediction, probability = predict_heart_disease(features)

print("Symptoms:", symptoms)
print("Generated Features:", features)
print("Heart Disease Prediction:", prediction)
print("Probability:", probability)