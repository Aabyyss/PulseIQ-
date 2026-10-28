def map_symptoms_to_features(symptoms):
    """
    Maps detected symptom labels to clinical model features.

    Encodings follow the UCI source's own codebook (`heart-disease.names`),
    which is what the model is trained on:

    - `cp`: 1 typical angina, 2 atypical angina, 3 non-anginal pain,
      4 asymptomatic. Baseline is 4; a chest-pain cluster moves it to 1.
    - `slope`: 1 upsloping (normal), 2 flat, 3 downsloping.
    - `thal`: 3 normal, 6 fixed defect, 7 reversible defect.
    - `restecg`: 0 normal, 1 ST-T abnormality, 2 left ventricular hypertrophy.

    These are constraints, not preferences: the previous version emitted
    `cp=0` and `thal=1..2`, values that do not exist in the UCI encoding (they
    came from the shifted Kaggle copy). The model read them as absent evidence
    and 'crushing chest pain' scored Low. `test_feature_encoding.py` keeps every
    emitted value inside the codebook's domain.

    Shifts are then calibrated against the trained model:
    - No symptoms               -> Low band
    - Stable chest pain         -> Medium band
    - Chest pain + autonomic or radiation signs -> High band
    - SOB + fatigue             -> High band on the current model

    Those bands are asserted in `test_feature_encoding.py`; the model's
    probability scale is measured in `train_model.py`, so a retrain that moves
    a canonical presentation out of its band fails there rather than shipping.
    """
    features = {
        "age": 50,
        "sex": 1,
        "cp": 4,          # asymptomatic - no chest symptoms reported
        "trestbps": 125,
        "chol": 200,
        "fbs": 0,
        "restecg": 0,
        "thalach": 165,   # good exercise capacity
        "exang": 0,       # no exercise-induced angina
        "oldpeak": 0.0,   # no ST depression
        "slope": 1,       # upsloping = normal
        "ca": 0,          # no blocked vessels seen
        "thal": 3,        # normal scan result
    }

    s = set(symptoms)

    if "chest pain" in s:
        # Typical angina cluster: exertional pain with ischemic signs.
        features.update(
            {
                "age": 55,
                "cp": 1,          # typical angina
                "trestbps": 138,
                "chol": 230,
                "thalach": 135,   # reduced exercise capacity
                "exang": 1,       # exertional component
                "oldpeak": 1.8,   # ST depression
                "slope": 2,       # flat ST segment
                "ca": 1,          # one vessel involved
                "thal": 7,        # reversible defect
            }
        )

    if "shortness of breath" in s:
        features["age"] = max(features["age"], 57)
        features["trestbps"] = max(features["trestbps"], 142)
        features["chol"] = max(features["chol"], 240)
        features["thalach"] = min(features["thalach"], 118)
        features["oldpeak"] = max(features["oldpeak"], 2.2)
        features["ca"] = max(features["ca"], 2)
        features["thal"] = max(features["thal"], 6)  # fixed defect

    if "dizziness" in s:
        features["trestbps"] = max(features["trestbps"], 148)

    if "fatigue" in s:
        features["thalach"] = min(features["thalach"], 128)
        features["oldpeak"] = max(features["oldpeak"], 1.4)

    if "palpitations" in s:
        if features["restecg"] == 0:
            features["restecg"] = 1
        features["thal"] = max(features["thal"], 2)

    if "nausea" in s:
        # Nausea/vomiting accompany ischemic episodes; shifts toward the
        # atypical-presentation profile without dominating the encoding.
        features["age"] = max(features["age"], 54)
        features["chol"] = max(features["chol"], 225)

    if "sweating" in s:
        # Diaphoresis is an acute autonomic sign; pairs with angina
        # features (raised pressure, reduced capacity, ST changes).
        features["trestbps"] = max(features["trestbps"], 140)
        features["thalach"] = min(features["thalach"], 132)
        features["oldpeak"] = max(features["oldpeak"], 1.2)

    if "leg swelling" in s:
        # Dependent edema suggests elevated filling pressures / failing
        # pump: reduced capacity, ST depression, vessel involvement.
        # Calibrated so isolated edema lands in the Medium band (~0.71)
        # while varicose-vein-only complaints still warrant workup.
        features["age"] = max(features["age"], 58)
        features["trestbps"] = max(features["trestbps"], 138)
        features["chol"] = max(features["chol"], 235)
        features["thalach"] = min(features["thalach"], 125)
        features["oldpeak"] = max(features["oldpeak"], 1.6)
        features["ca"] = max(features["ca"], 2)
        features["thal"] = max(features["thal"], 6)  # fixed defect

    if "cough" in s:
        # Nocturnal cough flags pulmonary congestion; mild feature shift
        # so an isolated cough stays low-risk while adding to clusters.
        features["thalach"] = min(features["thalach"], 145)

    if "exercise pain" in s:
        features["exang"] = 1

    if "chest pain" in s and s & {"sweating", "radiating pain", "nausea"}:
        # Pain plus diaphoresis, radiation or nausea is the acute-coronary
        # picture, not stable single-symptom angina: more ischaemia, worse
        # exercise tolerance, a downsloping segment. Deliberately keyed on
        # signs that are documented in the presentation, not on model output.
        features["age"] = max(features["age"], 58)
        features["trestbps"] = max(features["trestbps"], 150)
        features["thalach"] = min(features["thalach"], 110)
        features["oldpeak"] = max(features["oldpeak"], 2.5)
        features["slope"] = 3        # downsloping ST segment
        features["ca"] = max(features["ca"], 2)
        features["thal"] = 7         # reversible defect
        features["restecg"] = 1      # ST-T abnormality

    return list(features.values())
