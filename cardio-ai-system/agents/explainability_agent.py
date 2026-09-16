import os
import pickle

import pandas as pd
import shap

# Load trained model (path resolved relative to this file, not cwd)
_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "models",
    "heart_model.pkl",
)

with open(_MODEL_PATH, "rb") as _model_file:
    model = pickle.load(_model_file)

# Feature names from heart dataset
feature_names = [
    "age", "sex", "cp", "trestbps", "chol", "fbs",
    "restecg", "thalach", "exang", "oldpeak",
    "slope", "ca", "thal"
]

# Create SHAP explainer
explainer = shap.TreeExplainer(model)


def explain_prediction(features):
    """
    Generates explanation for the model prediction.
    Handles both legacy (list of 2D arrays) and modern (3D array) SHAP outputs.
    """
    # Convert features to dataframe
    df = pd.DataFrame([features], columns=feature_names)

    # Compute SHAP values
    shap_values = explainer.shap_values(df)

    shap_vals = None
    if isinstance(shap_values, list):
        # Legacy format: [class0_matrix, class1_matrix]
        shap_vals = shap_values[-1][0]
    else:
        arr = shap_values
        # Modern format: (n_samples, n_features) or (n_samples, n_features, n_classes)
        if arr.ndim == 3:
            # Take the positive-class slice for the first (only) sample
            shap_vals = arr[0, :, -1]
        elif arr.ndim == 2:
            shap_vals = arr[0]
        else:
            shap_vals = arr

    # Flatten to plain python floats so sorting can never hit array ambiguity
    contributions = {
        feature: float(value)
        for feature, value in zip(feature_names, shap_vals)
    }

    # Sort features by importance
    sorted_features = sorted(
        contributions.items(),
        key=lambda x: abs(x[1]),
        reverse=True
    )

    # Take top 3 contributing features
    top_features = sorted_features[:3]

    explanation = []

    for feature, value in top_features:
        explanation.append({
            "feature": feature,
            "impact": value
        })

    return explanation