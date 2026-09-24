from __future__ import annotations


SYMPTOM_TO_ENTITIES = {
    "chest pain": ["SNOMED:29857009", "UMLS:C0008031"],
    "shortness of breath": ["SNOMED:267036007", "UMLS:C0013404"],
    "palpitations": ["SNOMED:80313002", "UMLS:C0030252"],
    "dizziness": ["SNOMED:404640003", "UMLS:C0012833"],
    "fatigue": ["SNOMED:84229001", "UMLS:C0015670"],
    "nausea": ["SNOMED:422587007", "UMLS:C0027497"],
    "sweating": ["SNOMED:30786003", "UMLS:C0038990"],
    "leg swelling": ["SNOMED:38948008", "UMLS:C0013604"],
    "cough": ["SNOMED:49727002", "UMLS:C0010200"],
}


def link_medical_entities(symptoms: list[str]) -> dict:
    linked = {}
    for symptom in symptoms:
        if symptom in SYMPTOM_TO_ENTITIES:
            linked[symptom] = SYMPTOM_TO_ENTITIES[symptom]
    return linked
