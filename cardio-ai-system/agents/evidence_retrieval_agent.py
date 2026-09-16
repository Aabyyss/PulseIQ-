from __future__ import annotations


def retrieve_evidence_snippets(symptoms: list[str], report_text: str) -> list[dict]:
    items = []
    if "chest pain" in symptoms:
        items.append(
            {
                "topic": "Acute chest pain triage",
                "summary": "Early ECG and troponin trend are core elements of acute chest pain risk stratification.",
            }
        )
    if "shortness of breath" in symptoms:
        items.append(
            {
                "topic": "Dyspnea differential",
                "summary": "Cardiac and pulmonary causes should be assessed simultaneously in acute dyspnea.",
            }
        )
    if "troponin" in report_text.lower():
        items.append(
            {
                "topic": "Troponin interpretation",
                "summary": "Dynamic troponin change with clinical context improves specificity for myocardial injury.",
            }
        )
    return items[:3]
