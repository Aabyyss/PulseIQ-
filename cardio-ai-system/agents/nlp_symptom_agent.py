import spacy

try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    # Fallback keeps server booting even if model isn't installed yet.
    nlp = spacy.blank("en")

symptom_dictionary = {
    "chest pain": [
        "chest pain", "chest pressure", "chest tightness",
        "سینے میں درد", "سینے کا درد", "seene mein dard"
    ],
    "shortness of breath": [
        "shortness of breath", "breathing difficulty", "breathlessness",
        "سانس پھولنا", "سانس لینے میں تکلیف", "saans phoolna"
    ],
    "dizziness": [
        "dizziness", "lightheaded", "faint",
        "چکر", "chakkar"
    ],
    "palpitations": [
        "palpitations", "irregular heartbeat", "heart racing",
        "دل کی دھڑکن تیز", "dil ki dharkan tez"
    ],
    "fatigue": [
        "fatigue", "tiredness", "weakness",
        "کمزوری", "thakan", "kamzori"
    ]
}

def extract_symptoms_from_text(text):
    _ = nlp(text.lower())

    detected = []

    for symptom, phrases in symptom_dictionary.items():
        for phrase in phrases:
            if phrase in text.lower():
                detected.append(symptom)

    return list(set(detected))
