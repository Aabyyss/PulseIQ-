import os
import pickle

import pandas as pd

# Host Application Control policies can block sklearn's libsvm extension;
# probe once and degrade inertly so RandomForest inference still loads
# (the blocked file is never executed). See agents/sklearn_compat.py.
from agents.sklearn_compat import ensure_sklearn_importable

ensure_sklearn_importable()

_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "models",
    "heart_model.pkl",
)

with open(_MODEL_PATH, "rb") as _model_file:
    model = pickle.load(_model_file)

feature_names = [
    "age", "sex", "cp", "trestbps", "chol", "fbs",
    "restecg", "thalach", "exang", "oldpeak",
    "slope", "ca", "thal"
]


def predict_heart_disease(features):
    df = pd.DataFrame([features], columns=feature_names)

    prediction = model.predict(df)

    probability = model.predict_proba(df)

    return prediction[0], probability[0][1]
