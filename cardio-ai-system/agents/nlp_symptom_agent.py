import re

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

# Surface phrases mapped to clinical concepts, in three registers:
# clinical English, the patient's own English words, and Urdu (script +
# Roman). Matching is lowercase substring, so entries double as stems:
# "chakkar" catches "chakkar aa rahe hain" and "heart racing" catches
# "my heart is racing". Bare high-collision stems ("tired", "weak",
# "dard") are deliberately excluded — bare "tired" would even match
# "retired" — and only collocations unlikely in unrelated sentences
# ("feel tired", "seene mein dard") are used.

# A few everyday patient words are too collision-prone for substring
# matching ("tired" also sits inside "retired") yet too common to list
# in every collocation, so they match as whole words only.
_WORD_STEMS = {
    "fatigue": ("tired", "weak"),
}
_WORD_STEM_RES = {
    symptom: [re.compile(rf"\b{re.escape(stem)}\b") for stem in stems]
    for symptom, stems in _WORD_STEMS.items()
}
symptom_dictionary = {
    "chest pain": [
        "chest pain", "chest pressure", "chest tightness", "chest discomfort",
        "chest hurts", "chest feels heavy", "tight chest",
        "pain in my chest", "pain in the chest", "pain in chest",
        "pressure in my chest", "pressure in chest", "heaviness in my chest",
        "heaviness in chest", "burning in my chest", "angina",
        # Urdu script + Roman Urdu
        "سینے میں درد", "سینے کا درد", "چھاتی میں درد", "سینے میں جلن",
        "seene mein dard", "seenay mein dard", "seene mein darad",
        "chati mein dard", "seene mein jalan"
    ],
    "shortness of breath": [
        "shortness of breath", "breathing difficulty", "breathlessness",
        "short of breath", "out of breath", "breathless",
        "difficulty breathing", "trouble breathing",
        "can't breathe", "cant breathe", "cannot breathe",
        "hard to breathe",
        "سانس پھولنا", "سانس پھول", "سانس لینے میں تکلیف", "سانس چڑھنا",
        "سانس کی تکلیف",
        "saans phoolna", "saans phool", "sans phool",
        "saans lene", "saans chadh", "saans ki takleef"
    ],
    "dizziness": [
        "dizziness", "dizzy", "lightheaded", "light-headed", "lightheadedness",
        "faint", "fainting", "fainted", "passing out", "passed out",
        "about to pass out", "blacked out", "blackout", "vertigo",
        "room is spinning",
        "چکر", "چکر آ", "سر گھوم",
        "chakkar", "chakker", "sir ghoom", "sar ghoom"
    ],
    "palpitations": [
        "palpitations", "irregular heartbeat", "skipped beats",
        "heart racing", "heart is racing", "racing heart",
        "heart pounding", "heart is pounding", "pounding heart",
        "heart beating fast", "heart is beating fast", "beating fast",
        "heart thumping", "heart is thumping", "heartbeat fast",
        "heart flutter", "heart fluttering", "heart skipping",
        "دل کی دھڑکن تیز", "دھڑکن تیز", "دل کی دھڑکن",
        "dil ki dharkan tez", "dharkan tez", "dil ki dhadkan", "dhadkan tez",
        "dil dhark"
    ],
    "fatigue": [
        "fatigue", "fatigued", "tiredness", "exhausted", "exhaustion",
        "lethargic", "lethargy", "worn out",
        "feel tired", "feels tired", "feeling tired",
        "very tired", "so tired", "too tired", "am tired",
        "im tired", "i'm tired", "always tired", "tired all the time",
        "getting tired", "tires easily", "tire easily",
        "weakness", "feel weak", "feels weak", "feeling weak",
        "weak all the time", "no energy", "low energy", "loss of energy",
        "no strength",
        "کمزوری", "کمزور", "تھکن", "تھکاوٹ", "تھکا ہوا", "تھک گیا", "تھک گئی",
        "thakan", "thakan rehti", "kamzori", "kamzor",
        "thak jata", "thak jati", "thak gaya", "thak gayi",
        "thaka hua", "thaki hui"
    ],
    "nausea": [
        "nausea", "nauseous", "queasy", "queasiness",
        "feel sick", "feeling sick", "felt sick",
        "want to throw up", "vomiting", "vomited",
        "throwing up", "threw up", "puking", "puked",
        "urge to vomit", "sick to my stomach",
        "matli", "ji matli", "matli si", "ulati", "ulti aayi",
        "ultian", "qay", "qay aayi",
        "متلی", "جی متلی", "الٹی", "الٹیاں", "قے"
    ],
    "sweating": [
        "sweating", "sweaty", "diaphoresis", "diaphoretic",
        "cold sweat", "night sweats", "drenched in sweat",
        "breaking out in a sweat", "covered in sweat",
        "pasina", "pasine", "pasina aa", "pasina chal",
        "پسینہ", "پسینے", "پسینہ آ"
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
    words = _split_words(text_lower)

    for symptom, phrases in symptom_dictionary.items():
        for phrase in phrases:
            start = 0
            while True:
                pos = text_lower.find(phrase, start)
                if pos == -1:
                    break
                start = pos + 1
                if _is_negated(text_lower, pos, words):
                    continue
                if symptom not in detected:
                    detected.append(symptom)
                    details[symptom] = phrase
                break

    # Whole-word pass for stems excluded from substring matching.
    for symptom, patterns in _WORD_STEM_RES.items():
        if symptom in detected:
            continue
        for pattern in patterns:
            for match in pattern.finditer(text_lower):
                if _is_negated(text_lower, match.start(), words):
                    continue
                detected.append(symptom)
                details[symptom] = match.group()
                break
            if symptom in detected:
                break

    detected = list(set(detected))
    if return_details:
        return detected, details
    return detected
