from __future__ import annotations


SYMPTOM_TO_ENTITIES = {
    "chest pain": ["SNOMED:29857009", "UMLS:C0008031"],
    "shortness of breath": ["SNOMED:267036007", "UMLS:C0013404"],
    "palpitations": ["SNOMED:80313002", "UMLS:C0030252"],
    "dizziness": ["SNOMED:404640003", "UMLS:C0012833"],
}


def link_medical_entities(symptoms: list[str]) -> dict:
    linked = {}
    for symptom in symptoms:
        if symptom in SYMPTOM_TO_ENTITIES:
            linked[symptom] = SYMPTOM_TO_ENTITIES[symptom]
    return linked
