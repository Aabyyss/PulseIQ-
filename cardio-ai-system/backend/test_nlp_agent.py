import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.nlp_symptom_agent import extract_symptoms_from_text

text = "I feel chest pressure and breathing difficulty when walking upstairs"

symptoms = extract_symptoms_from_text(text)

print("Detected Symptoms:", symptoms)