from __future__ import annotations

from typing import List


RED_FLAG_KEYWORDS = [
    "crushing pain",
    "severe chest pain",
    "fainting",
    "passed out",
    "sweating",
    "cold sweat",
    "jaw pain",
    "left arm pain",
]


def suggest_next_questions(symptoms: List[str], transcript: str) -> list[str]:
    questions = [
        "Can you describe when the symptoms started and how long each episode lasts?",
        "Does the pain worsen with exertion and improve with rest?",
        "On a scale of 0 to 10, how severe is the discomfort right now?",
    ]

    lowered = transcript.lower()

    if "shortness of breath" in symptoms:
        questions.append("Do you feel breathless while lying flat or only during activity?")
    if "palpitations" in symptoms:
        questions.append("Have you noticed irregular beats, skipped beats, or very fast heart rate episodes?")
    if "dizziness" in symptoms:
        questions.append("Did dizziness occur with loss of consciousness or near-fainting?")

    if any(keyword in lowered for keyword in RED_FLAG_KEYWORDS):
        questions.insert(0, "Any current severe chest pressure, fainting, or pain spreading to jaw/arm right now?")

    return questions[:5]


def recommend_for_patient(risk_level: str, transcript: str) -> list[str]:
    recommendations = [
        "Avoid strenuous activity until evaluated by a clinician.",
        "Track symptom episodes (trigger, duration, severity) for clinical review.",
        "Stay hydrated and avoid excessive caffeine or nicotine.",
    ]

    lowered = transcript.lower()
    high_urgency = risk_level == "High" or any(keyword in lowered for keyword in RED_FLAG_KEYWORDS)

    if high_urgency:
        return [
            "Seek urgent medical evaluation immediately.",
            "If severe ongoing chest pain, breathing distress, or fainting is present, call emergency services now.",
            "Do not drive yourself if symptoms are severe; use emergency transport.",
        ]

    if risk_level == "Medium":
        recommendations.insert(0, "Book same-day or next-day medical evaluation.")

    return recommendations[:4]
