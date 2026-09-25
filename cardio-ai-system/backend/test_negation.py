"""Negation-aware symptom extraction tests.

Also covers the expanded patient-phrase dictionary (casual English,
Roman Urdu and Urdu script) added after the matcher only recognised
clinical phrasings.

Run directly (matching the CI style):
    python backend/test_negation.py
"""

import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.nlp_symptom_agent import extract_symptoms_from_text

CASES = [
    # (narrative, expected positive concepts)
    ("I feel chest pressure and breathing difficulty when walking upstairs",
     {"chest pain", "shortness of breath"}),
    ("no chest pain on exertion", set()),
    ("denies chest pain and shortness of breath", set()),
    ("no chest pain, no palpitations", set()),
    ("patient has no chest pain but does have palpitations", {"palpitations"}),
    ("ruled out shortness of breath; reports dizziness", {"dizziness"}),
    ("resolved chest tightness, new episode of faint", {"dizziness"}),
    ("crushing chest pain radiating to left arm", {"chest pain"}),
    ("Denies chest pain. Reports an episode of faint last week.", {"dizziness"}),
    ("", set()),
    # Roman-Urdu negation cues
    ("nahi hai thakan", set()),
    ("koi dard nahi", set()),
    # "but" flips polarity: it must stop the negation window instead of
    # leaking the cue across the contrast (regression for the window fix).
    ("no nausea but severe sweating", {"sweating"}),
    ("no chest pain but severe dizziness", {"dizziness"}),
    ("no dizziness but chest pain at night", {"chest pain"}),
]

# Patient-phrasing extraction: casual English, Roman Urdu, Urdu script.
PHRASE_CASES = [
    ("hello i have chest pain and dizziness", {"chest pain", "dizziness"}),
    ("I feel dizzy and tired", {"dizziness", "fatigue"}),
    ("heart is racing", {"palpitations"}),
    ("feeling weak since morning", {"fatigue"}),
    ("I am sweating and nauseous with chest discomfort", {"chest pain", "nausea", "sweating"}),
    ("i can't breathe properly when i lie down", {"shortness of breath"}),
    ("i passed out at the market yesterday", {"dizziness"}),
    ("my chest feels heavy", {"chest pain"}),
    ("having trouble breathing at night", {"shortness of breath"}),
    ("heart pounding while resting", {"palpitations"}),
    ("mujhe chakkar aa rahe hain", {"dizziness"}),
    ("dil ki dharkan tez ho rahi hai", {"palpitations"}),
    ("saans lene mein taklif hai", {"shortness of breath"}),
    ("seene mein dard hai", {"chest pain"}),
    ("thakan rehti hai din bhar", {"fatigue"}),
    ("سینے میں درد ہے", {"chest pain"}),
    ("مجھے سانس پھولنے کی تکلیف ہے", {"shortness of breath"}),
    ("مجھے چکر آ رہے ہیں", {"dizziness"}),
    ("دل کی دھڑکن تیز ہے", {"palpitations"}),
    ("مجھے کمزوری محسوس ہوتی ہے", {"fatigue"}),
    ("i feel nauseous and have been vomiting since morning", {"nausea"}),
    ("matli si rahi hai aur ulti aayi bhi", {"nausea"}),
    ("مجھے جی متلی ہو رہی ہے", {"nausea"}),
    ("cold sweat with drenching night sweats", {"sweating"}),
    ("pasina aa raha hai bohat", {"sweating"}),
    ("پسینہ آ رہا ہے اور چکر بھی", {"sweating", "dizziness"}),
    ("i feel great today", set()),
    # Radiation phrasings - patients name the destination, not the chest.
    # Orthopedic look-alikes must stay unmatched.
    ("crushing chest pain radiating to my left arm", {"chest pain"}),
    ("pain radiating to my jaw and i feel nauseous", {"chest pain", "nausea"}),
    ("dard jabre ki taraf ja raha hai", {"chest pain"}),
    ("my left arm hurts when i lift it", set()),
    ("i pulled a muscle in my back", set()),
    # Heart-failure signals: dependent edema and cough.
    ("swollen ankles and trouble breathing when lying flat", {"leg swelling", "shortness of breath"}),
    ("pairon mein sujan hai", {"leg swelling"}),
    ("ٹانگوں میں سوجن ہے", {"leg swelling"}),
    ("پیٹ میں سوجن ہے", set()),
    ("persistent cough worse at night", {"cough"}),
    ("کھانسی ہو رہی ہے", {"cough"}),
    ("no cough but swollen feet", {"leg swelling"}),
    # No false triggers on unrelated words
    ("hello doctor", set()),
    ("i have a headache and fever", set()),
    ("he is retired", set()),
    # Patients localise cardiac pain to "the heart" (and ASR drops/stretches
    # words); these surfaced from real copilot transcripts.
    ("it pains in my heart twice a day", {"chest pain"}),
    ("and it pains in my heart sometimes", {"chest pain"}),
    ("it pains in the left side of my heart twice a day", {"chest pain"}),
    ("i have pain in my bag and in my left side of the heart", {"chest pain"}),
    ("there is a stabbing pain in my heart area", {"chest pain"}),
    ("my heart hurts when i climb stairs", {"chest pain"}),
    ("dil mein dard hota hai", {"chest pain"}),
    ("دل میں درد ہے", {"chest pain"}),
    ("heart pain after walking", {"chest pain"}),
    ("right side of my chest aches at night", {"chest pain"}),
    # Urdu-script orthography variants: arabic yeh/heh codepoints must
    # still match (normalisation unifies them with the Urdu forms).
    ("دل ميں درد ہے", {"chest pain"}),
    # Urdu negation sits AFTER the noun phrase ("dard NAHI hai") and must
    # not leak into the next symptom.
    ("دل کا درد نہیں ہے", set()),
    ("دل میں درد نہیں", set()),
    ("dil ka dard nahi hai", set()),
    ("the chest pain has resolved", set()),
    ("the chest pain is gone now", set()),
    # "without" after a phrase denies the FOLLOWING symptom, not the
    # preceding one (the post-window carries only symptom-ceasing cues).
    ("chest pain without sweating", {"chest pain"}),
    ("سینے میں درد ہے اور پسینہ آ رہا ہے", {"chest pain", "sweating"}),
    ("دل میں درد ہے لیکن سانس پھول رہی ہے", {"chest pain", "shortness of breath"}),
]


def run_phrase_cases() -> int:
    failures = 0
    for text, expected in PHRASE_CASES:
        got = set(extract_symptoms_from_text(text))
        if got != expected:
            failures += 1
            print(f"FAIL: {text!r} -> {sorted(got)}, expected {sorted(expected)}")
    return failures


def main() -> int:
    failures = 0
    for text, expected in CASES:
        got = set(extract_symptoms_from_text(text))
        if got != expected:
            failures += 1
            print(f"FAIL: {text!r} -> {sorted(got)}, expected {sorted(expected)}")

    # Details mode: matched surface phrases returned for transparency.
    symptoms, details = extract_symptoms_from_text(
        "no chest pain, yes dizziness", return_details=True
    )
    if symptoms != ["dizziness"] or details != {"dizziness": "dizziness"}:
        failures += 1
        print(f"FAIL: details mode -> {symptoms}, {details}")

    failures += run_phrase_cases()

    if failures:
        print(f"{failures} negation/extraction test(s) failed")
        return 1
    print("All negation and extraction tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
