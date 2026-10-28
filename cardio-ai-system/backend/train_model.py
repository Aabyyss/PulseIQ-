"""Train the PulseIQ heart-disease screening model.

Two defects live in the public `heart.csv` that this project trains on, and both
are handled here rather than in prose:

1. **Inverted target** (fixed 2026-09): in the raw file `target=1` rows are the
   HEALTHY group and `target=0` rows are the DISEASE group, verifiable from
   feature means (target=1 rows have higher exercise capacity, less ST
   depression, fewer blocked vessels). The label is flipped so class 1 = disease
   everywhere in PulseIQ.

2. **Duplicate rows** (fixed 2026-10): the file has 1,025 rows but only 302
   distinct feature vectors — 723 rows are exact copies. Splitting before
   de-duplicating leaks test rows into training: the same patient profile lands
   in both halves, the model memorises it, and the holdout reports ROC-AUC 1.000
   and recall 1.000. That number was real arithmetic and worthless evidence.
   The data is de-duplicated *before* the split, so no feature vector appears on
   both sides, and the metadata records the split rule next to the metrics.

Both guards are asserted at the end of training, so a future edit that
reintroduces either defect fails loudly instead of shipping a better-looking
number.
"""

import json
import pickle
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # `python backend/train_model.py` must find `agents/`
    sys.path.insert(0, str(ROOT))

from agents.sklearn_compat import ensure_sklearn_importable

ensure_sklearn_importable()

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import (
    StratifiedKFold,
    cross_val_predict,
    cross_val_score,
    train_test_split,
)

from backend.calibration import calibration_summary, format_reliability_table

DATA_PATH = ROOT / "data" / "heart.csv"
MODEL_PATH = ROOT / "models" / "heart_model.pkl"
META_PATH = ROOT / "models" / "heart_model_meta.json"

TEST_SIZE = 0.2
RANDOM_STATE = 42
CV_FOLDS = 10
CALIBRATION_BINS = 10

_SPLIT_RULE = (
    "Exact duplicate rows removed before splitting (drop_duplicates), then a single "
    f"stratified {int((1 - TEST_SIZE) * 100)}/{int(TEST_SIZE * 100)} train/test split "
    f"(random_state={RANDOM_STATE}) on the distinct feature vectors. Metrics are on that "
    f"held-out split; a {CV_FOLDS}-fold stratified CV is reported alongside for stability. "
    "Duplicates are never shared between train and test."
)


def load_dataset(path: Path = DATA_PATH) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return `(raw, unique)` — the file as shipped, and its distinct rows.

    Kept separate and importable so the de-duplication is testable without
    retraining: a test can assert that the frame handed to the splitter has no
    repeated feature vector.
    """
    raw = pd.read_csv(path)
    unique = raw.drop_duplicates().reset_index(drop=True)
    return raw, unique


def labels(frame: pd.DataFrame) -> pd.Series:
    """1 = disease. The source file has the polarity reversed (see module docstring)."""
    return 1 - frame["target"]


def split_dataset(
    frame: pd.DataFrame, test_size: float = TEST_SIZE, random_state: int = RANDOM_STATE
):
    """Split *distinct* rows into train/test, stratified on the flipped label."""
    y = labels(frame)
    X = frame.drop("target", axis=1)
    return train_test_split(X, y, test_size=test_size, random_state=random_state, stratify=y)


def _tuple_rows(frame: pd.DataFrame) -> set[tuple]:
    return {tuple(row) for row in frame.itertuples(index=False, name=None)}


def main() -> None:
    raw, data = load_dataset()

    duplicates = len(raw) - len(data)
    print(f"Rows         : {len(raw)} shipped, {len(data)} distinct ({duplicates} exact duplicates dropped)")
    assert not data.duplicated().any(), "duplicate feature vectors survived de-duplication"

    X_train, X_test, y_train, y_test = split_dataset(data)

    # A split is only honest if no profile appears on both sides. With exact
    # duplicates this is the whole failure mode, so assert it directly.
    overlap = _tuple_rows(X_train) & _tuple_rows(X_test)
    assert not overlap, f"{len(overlap)} feature vectors appear in both train and test"

    model = RandomForestClassifier(n_estimators=300, random_state=RANDOM_STATE)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]

    holdout = {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "precision": float(precision_score(y_test, y_pred)),
        "recall": float(recall_score(y_test, y_pred)),
        "f1": float(f1_score(y_test, y_pred)),
        "roc_auc": float(roc_auc_score(y_test, y_proba)),
    }

    print(f"Holdout      : {len(X_test)} rows")
    for name, value in holdout.items():
        print(f"  {name:<10}: {value:.3f}")

    X_all, y_all = data.drop("target", axis=1), labels(data)
    cv = StratifiedKFold(CV_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    for metric in ("accuracy", "roc_auc"):
        scores = cross_val_score(model, X_all, y_all, cv=cv, scoring=metric)
        print(f"{CV_FOLDS}-fold {metric}: {scores.mean():.3f} +/- {scores.std():.3f}")
        holdout[f"cv_{metric}"] = float(scores.mean())
        holdout[f"cv_{metric}_std"] = float(scores.std())

    # --- Calibration: does the probability mean what it says? ------------------
    # Out-of-fold probabilities are used rather than the 61-row holdout alone:
    # every distinct patient contributes one prediction made by a model that
    # never saw them, which is the same guarantee with five times the sample.
    oof_prob = cross_val_predict(model, X_all, y_all, cv=cv, method="predict_proba")[:, 1]
    oof = calibration_summary(y_all.tolist(), oof_prob.tolist(), n_bins=CALIBRATION_BINS)
    holdout_calibration = calibration_summary(
        y_test.tolist(), y_proba.tolist(), n_bins=CALIBRATION_BINS
    )

    print(f"Calibration  : out-of-fold, n={oof['n']}")
    print(f"  Brier score: {oof['brier']:.3f} (0.25 = always predicting 0.5)")
    print(f"  ECE        : {oof['ece']:.3f} over {oof['bins']} bins")
    print(f"  Base rate  : {oof['base_rate']:.3f} disease | mean predicted {oof['mean_predicted']:.3f}")
    print(format_reliability_table(oof))

    # A probability that cannot be trusted on the probability scale must not be
    # published as if it could: 0.25 is the no-skill Brier score.
    assert oof["brier"] < 0.25, f"Brier {oof['brier']:.3f} is no better than predicting 0.5"

    # --- Regression guard: textbook profiles must classify correctly ------------
    feature_names = list(X_train.columns)
    disease_like = [[62, 1, 3, 145, 260, 1, 2, 120, 1, 2.5, 1, 2, 3]]
    healthy_like = [[45, 0, 0, 120, 200, 0, 0, 172, 0, 0.0, 2, 0, 1]]
    p_dis = model.predict_proba(pd.DataFrame(disease_like, columns=feature_names))[0][1]
    p_hea = model.predict_proba(pd.DataFrame(healthy_like, columns=feature_names))[0][1]
    print(f"Sanity       : disease-like P(disease)={p_dis:.2f} | healthy-like P(disease)={p_hea:.2f}")
    assert p_dis > 0.7, "DISEASE-like profile must score high - label flip regression!"
    assert p_hea < 0.3, "HEALTHY-like profile must score low - label flip regression!"

    # --- Persist model + metadata ----------------------------------------------
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)

    meta = {
        "name": "PulseIQ heart-disease screening model",
        "algorithm": "RandomForestClassifier(n_estimators=300, random_state=42)",
        "trained_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "sklearn_version": __import__("sklearn").__version__,
        "dataset": "data/heart.csv (public heart dataset)",
        "dataset_rows": len(raw),
        "dataset_unique_rows": len(data),
        "dataset_duplicate_rows": duplicates,
        "split": _SPLIT_RULE,
        "n_train": len(X_train),
        "n_test": len(X_test),
        "target_encoding": "1 = disease, 0 = healthy (source labels were inverted and flipped)",
        "features": list(X_train.columns),
        "metrics": {key: round(value, 3) for key, value in holdout.items()},
        "calibration": {
            "out_of_fold": {key: round(value, 3) for key, value in oof.items() if key != "reliability"},
            "holdout": {
                key: round(value, 3)
                for key, value in holdout_calibration.items()
                if key != "reliability"
            },
            "reliability": [
                {
                    "bin": f"{entry['lower']:.1f}-{entry['upper']:.1f}",
                    "count": entry["count"],
                    "mean_predicted": None
                    if entry["mean_predicted"] is None
                    else round(entry["mean_predicted"], 3),
                    "observed_rate": None
                    if entry["observed_rate"] is None
                    else round(entry["observed_rate"], 3),
                }
                for entry in oof["reliability"]
            ],
        },
        "metrics_note": (
            "Metrics come from distinct rows only. Earlier revisions reported ROC-AUC and "
            "recall of 1.000 because 723 of 1,025 rows were exact duplicates split across "
            "train and test; that figure is withdrawn, not reproduced here. Calibration "
            "(Brier, ECE) is measured on out-of-fold predictions, one per distinct patient."
        ),
    }
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print("Saved models/heart_model.pkl + models/heart_model_meta.json")


if __name__ == "__main__":
    main()
