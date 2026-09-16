from __future__ import annotations


def generate_counterfactuals(symptoms: list[str]) -> list[str]:
    suggestions = []
    if "chest pain" in symptoms:
        suggestions.append("If exertional chest pain is absent, ischemic likelihood may decrease.")
    if "shortness of breath" in symptoms:
        suggestions.append("If dyspnea is positional/orthopnea, heart failure pathway becomes more likely.")
    if "palpitations" in symptoms:
        suggestions.append("If ECG confirms arrhythmia, rhythm etiology can dominate symptom explanation.")
    if not suggestions:
        suggestions.append("Need richer temporal symptom context for strong causal hypotheses.")
    return suggestions[:3]
