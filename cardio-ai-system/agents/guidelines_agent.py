from __future__ import annotations


def check_guideline_alignment(symptoms: list[str], report_text: str) -> list[str]:
    report = report_text.lower()
    checks = []
    if "chest pain" in symptoms:
        checks.append("Chest pain protocol: obtain ECG within 10 minutes and serial cardiac biomarkers.")
    if "shortness of breath" in symptoms:
        checks.append("Dyspnea protocol: pulse oximetry, respiratory exam, and cardiac/pulmonary differential.")
    if "troponin" in report:
        checks.append("Troponin trend protocol: repeat measurements and correlate with symptom timeline.")
    if not checks:
        checks.append("No specific protocol trigger identified; continue structured history and exam.")
    return checks[:4]
