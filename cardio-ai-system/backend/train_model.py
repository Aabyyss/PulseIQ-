import pickle
import time

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split

"""
Trains the PulseIQ heart-disease screening model.

IMPORTANT LABEL FIX (2026-09):
The public "heart.csv" used here ships with an INVERTED target column:
in the raw file, target=1 rows are the HEALTHY group and target=0 rows are
the DISEASE group (verifiable from feature means: target=1 rows have higher
exercise capacity, less ST depression, fewer blocked vessels).
We flip the label (y = 1 - target) so that class 1 = DISEASE everywhere
in PulseIQ. The textbook sanity profiles below guard against regressions.
"""

data = pd.read_csv("data/heart.csv")

X = data.drop("target", axis=1)
y = 1 - data["target"]  # flip inverted source labels -> 1 = disease

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

model = RandomForestClassifier(n_estimators=300, random_state=42)
model.fit(X_train, y_train)

y_pred = model.predict(X_test)
y_proba = model.predict_proba(X_test)[:, 1]

print("Accuracy :", round(accuracy_score(y_test, y_pred), 3))
print("Precision:", round(precision_score(y_test, y_pred), 3))
print("Recall   :", round(recall_score(y_test, y_pred), 3))
print("F1 Score :", round(f1_score(y_test, y_pred), 3))
print("ROC-AUC  :", round(roc_auc_score(y_test, y_proba), 3))

cv = StratifiedKFold(5, shuffle=True, random_state=42)
print("5-fold CV accuracy:", [round(s, 3) for s in cross_val_score(model, X, y, cv=cv)])

# --- Regression guard: textbook profiles must classify correctly ------------
feature_names = list(X.columns)
disease_like = [[62, 1, 3, 145, 260, 1, 2, 120, 1, 2.5, 1, 2, 3]]
healthy_like = [[45, 0, 0, 120, 200, 0, 0, 172, 0, 0.0, 2, 0, 1]]
p_dis = model.predict_proba(pd.DataFrame(disease_like, columns=feature_names))[0][1]
p_hea = model.predict_proba(pd.DataFrame(healthy_like, columns=feature_names))[0][1]
print(f"Sanity  : disease-like P(disease)={p_dis:.2f} | healthy-like P(disease)={p_hea:.2f}")
assert p_dis > 0.7, "DISEASE-like profile must score high - label flip regression!"
assert p_hea < 0.3, "HEALTHY-like profile must score low - label flip regression!"

# --- Persist model + metadata ----------------------------------------------
with open("models/heart_model.pkl", "wb") as f:
    pickle.dump(model, f)

meta = {
    "name": "PulseIQ heart-disease screening model",
    "algorithm": "RandomForestClassifier(n_estimators=300, random_state=42)",
    "trained_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    "sklearn_version": __import__("sklearn").__version__,
    "dataset": "data/heart.csv (public heart dataset, 1025 rows)",
    "target_encoding": "1 = disease, 0 = healthy (source labels were inverted and flipped)",
    "features": list(X.columns),
    "metrics": {
        "accuracy": round(float(accuracy_score(y_test, y_pred)), 3),
        "precision": round(float(precision_score(y_test, y_pred)), 3),
        "recall": round(float(recall_score(y_test, y_pred)), 3),
        "f1": round(float(f1_score(y_test, y_pred)), 3),
        "roc_auc": round(float(roc_auc_score(y_test, y_proba)), 3),
    },
}
with open("models/heart_model_meta.json", "w", encoding="utf-8") as f:
    import json

    json.dump(meta, f, indent=2)

print("Saved models/heart_model.pkl + models/heart_model_meta.json")
