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
    # Symptom-specific questions come first (ordered by acute-cardiac
    # priority, cough last) so the 5-question cap drops the lowest-yield
    # item rather than the ones matching the actual presentation.
    specific = []

    if "shortness of breath" in symptoms:
        specific.append("Do you feel breathless while lying flat or only during activity?")
    if "sweating" in symptoms:
        specific.append("Was the sweating a cold sweat that came on with the episode?")
    if "nausea" in symptoms:
        specific.append("Is the nausea with actual vomiting, and did it start with the pain?")
    if "palpitations" in symptoms:
        specific.append("Have you noticed irregular beats, skipped beats, or very fast heart rate episodes?")
    if "dizziness" in symptoms:
        specific.append("Did dizziness occur with loss of consciousness or near-fainting?")
    if "leg swelling" in symptoms:
        specific.append("Is the leg swelling worse by evening, and does it pit when pressed?")
    if "cough" in symptoms:
        specific.append("Is the cough worse at night or when lying flat, and is it dry or productive?")

    base = [
        "Can you describe when the symptoms started and how long each episode lasts?",
        "Does the pain worsen with exertion and improve with rest?",
        "On a scale of 0 to 10, how severe is the discomfort right now?",
        "Any nausea, sweating, or breathlessness alongside the discomfort?",
    ]

    questions = specific + base
    if len(questions) > 5:
        questions = questions[:5]

    lowered = transcript.lower()
    if any(keyword in lowered for keyword in RED_FLAG_KEYWORDS):
        questions.insert(0, "Any current severe chest pressure, fainting, or pain spreading to jaw/arm right now?")
        questions = questions[:5]

    return questions


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
