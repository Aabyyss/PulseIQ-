try:
    import spacy

    try:
        nlp = spacy.load("en_core_web_sm")
    except (OSError, ImportError):
        # Fallback keeps server booting even if model isn't installed yet.
        nlp = spacy.blank("en")
except ImportError:
    # spaCy itself unavailable (e.g. blocked DLLs): the dictionary matcher
    # below does the real work, so degrade to a no-op tokenizer.
    nlp = None

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

# Cues that flip a nearby symptom mention into a negated (denied) finding.
# Matched case-insensitively against the words immediately preceding the
# symptom phrase inside the negation window.
_NEGATION_CUES = (
    "no", "not", "denies", "deny", "denied", "without", "never",
    "nil", "free of", "resolved", "ruled out", "negative for",
    "no evidence of", "não tem",  # common transcript artifact kept for safety
)

# English cue equivalents clinicians commonly dictate in Roman Urdu.
_ROMAN_NEGATION_CUES = ("nahi", "nahin", "koi")

# How many meaningful words before a match may contain a cue and still
# apply. Connector words ("and", "or", commas) don't count toward the
# window, so a dictated list like "denies chest pain and shortness of
# breath" negates both findings.
_NEGATION_WINDOW_WORDS = 3
_CONNECTORS = {"and", "or", "but", ",", ";", "+"}


def _split_words(lower_text):
    return lower_text.split()


def _char_index_to_word_index(text_lower, char_pos):
    """Map a character offset to the index of the word containing it."""
    words = _split_words(text_lower)
    pos = 0
    for idx, word in enumerate(words):
        end = pos + len(word)
        if pos <= char_pos < end or char_pos == end and not word:
            return idx
        # account for the separator consumed between words
        pos = end + 1
    return len(words) - 1 if words else 0


def _is_negated(text_lower, phrase_char_pos, words):
    """True if a negation cue sits within the window before this phrase.

    Connector tokens are transparent: they don't consume window distance,
    so cues apply across list conjunctions.
    """
    word_idx = _char_index_to_word_index(text_lower, phrase_char_pos)
    window = []
    idx = word_idx - 1
    while idx >= 0 and len(window) < _NEGATION_WINDOW_WORDS:
        token = words[idx]
        if token not in _CONNECTORS:
            window.append(token)
        idx -= 1
    for cue in _NEGATION_CUES + _ROMAN_NEGATION_CUES:
        if not cue:
            continue
        if " " in cue:
            if cue in " ".join(reversed(window)):
                return True
        elif cue in window:
            return True
    return False


def extract_symptoms_from_text(text, return_details=False):
    """Extract cardiac symptom concepts from a narrative.

    Negation-aware: a mention preceded within three words by a cue such as
    "no", "denies" or "ruled out" is excluded from the positive findings.
    Returns the list of detected symptoms, or (list, details) when
    ``return_details`` is set, where details maps each symptom to its
    matched surface phrase for transparency.
    """
    text_lower = (text or "").lower()
    if nlp is not None:
        _ = nlp(text_lower)

    detected = []
    details = {}

    for symptom, phrases in symptom_dictionary.items():
        for phrase in phrases:
            start = 0
            while True:
                pos = text_lower.find(phrase, start)
                if pos == -1:
                    break
                start = pos + 1
                if _is_negated(text_lower, pos, _split_words(text_lower)):
                    continue
                if symptom not in detected:
                    detected.append(symptom)
                    details[symptom] = phrase
                break

    detected = list(set(detected))
    if return_details:
        return detected, details
    return detected
