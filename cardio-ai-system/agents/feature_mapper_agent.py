def map_symptoms_to_features(symptoms):
    """
    Maps detected symptom labels to clinical model features.

    Calibrated empirically against the retrained model (see train_model.py):
    - No symptoms        -> P(disease) ~0.05-0.13 (Low)
    - Chest pain cluster -> P(disease) ~0.98     (High)
    - SOB + fatigue      -> P(disease) ~0.45     (Medium)

    Encoding note (learned from this dataset): cp=0 is "typical angina" and is
    disease-leaning; cp=3 is "asymptomatic". The baseline therefore starts at
    cp=3 and a reported chest-pain cluster moves it to 0 with the classic
    angina feature pattern (exertional, ST depression, vessel involvement).

    The model was retrained with 1 = disease (source labels were inverted),
    so these feature shifts correctly raise P(disease).
    """
    features = {
        "age": 50,
        "sex": 1,
        "cp": 3,          # asymptomatic - no chest symptoms reported
        "trestbps": 125,
        "chol": 200,
        "fbs": 0,
        "restecg": 0,
        "thalach": 165,   # good exercise capacity
        "exang": 0,       # no exercise-induced angina
        "oldpeak": 0.0,   # no ST depression
        "slope": 2,
        "ca": 0,          # no blocked vessels seen
        "thal": 1,        # normal scan result
    }

    s = set(symptoms)

    if "chest pain" in s:
        # Typical angina cluster: exertional pain with ischemic signs.
        features.update(
            {
                "age": 55,
                "cp": 0,          # typical angina (disease-leaning in this encoding)
                "trestbps": 138,
                "chol": 230,
                "thalach": 135,   # reduced exercise capacity
                "exang": 1,       # exertional component
                "oldpeak": 1.8,   # ST depression
                "slope": 1,
                "ca": 1,          # one vessel involved
                "thal": 2,
            }
        )

    if "shortness of breath" in s:
        features["age"] = max(features["age"], 57)
        features["trestbps"] = max(features["trestbps"], 142)
        features["chol"] = max(features["chol"], 240)
        features["thalach"] = min(features["thalach"], 118)
        features["oldpeak"] = max(features["oldpeak"], 2.2)
        features["ca"] = max(features["ca"], 2)
        features["thal"] = max(features["thal"], 3)

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
        features["thal"] = max(features["thal"], 3)

    if "cough" in s:
        # Nocturnal cough flags pulmonary congestion; mild feature shift
        # so an isolated cough stays low-risk while adding to clusters.
        features["thalach"] = min(features["thalach"], 145)

    if "exercise pain" in s:
        features["exang"] = 1

    return list(features.values())
