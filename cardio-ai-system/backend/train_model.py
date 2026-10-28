"""Train the PulseIQ heart-disease screening model.

The data is the UCI Heart Disease (Cleveland) original, CC BY 4.0, rebuilt by
`scripts/import_uci_heart.py` from a checksum-pinned download; provenance and
attribution are in `data/heart_source.json` and `data/ATTRIBUTION.md`. It
replaced a widely circulated Kaggle copy that had two defects worth remembering
because both are now guarded against:

1. **Duplicate rows** — the Kaggle copy had 1,025 rows and only 302 distinct
   feature vectors. Splitting it before de-duplicating leaked test profiles into
   training and produced ROC-AUC 1.000. De-duplication now happens before the
   split, and the split is asserted disjoint.

2. **Label polarity** — that copy also inverted the target. The UCI original is
   the right way round (target 1 = disease), so nothing is flipped now; instead
   the data itself is checked against three clinical expectations (diseased
   patients have lower max heart rate, higher ST depression, more major vessels
   affected). A file whose labels were reversed would fail that check rather
   than quietly train backwards.

Both guards run before any metric is computed, so a future edit that
reintroduces either defect fails loudly instead of shipping a better-looking
number.
"""

import hashlib
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
SOURCE_PATH = ROOT / "data" / "heart_source.json"
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
    """1 = disease, as encoded by the importer from UCI `num > 0`."""
    return frame["target"].astype(int)


def validate_polarity(frame: pd.DataFrame) -> dict:
    """Raise unless the labels point the way cardiology says they should.

    These three directions hold in the Cleveland data and would all reverse if
    the label were inverted: disease carries a lower peak heart rate, deeper ST
    depression and more major vessels affected. Means, so a handful of odd
    records cannot flip the conclusion.
    """
    disease = frame[labels(frame) == 1]
    healthy = frame[labels(frame) == 0]
    if disease.empty or healthy.empty:
        raise ValueError("both classes must be present to verify label polarity")

    observed = {
        name: {
            "disease": float(disease[name].mean()),
            "healthy": float(healthy[name].mean()),
        }
        for name in ("thalach", "oldpeak", "ca")
    }
    if not observed["thalach"]["disease"] < observed["thalach"]["healthy"]:
        raise ValueError("label polarity: disease group has the higher max heart rate")
    if not observed["oldpeak"]["disease"] > observed["oldpeak"]["healthy"]:
        raise ValueError("label polarity: disease group has the lower ST depression")
    if not observed["ca"]["disease"] > observed["ca"]["healthy"]:
        raise ValueError("label polarity: disease group has fewer major vessels affected")
    return observed


def load_provenance(path: Path = SOURCE_PATH) -> dict:
    """The importer's record of where the data came from and how it was changed."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def split_dataset(
    frame: pd.DataFrame, test_size: float = TEST_SIZE, random_state: int = RANDOM_STATE
):
    """Split *distinct* rows into train/test, stratified on the label."""
    y = labels(frame)
    X = frame.drop("target", axis=1)
    return train_test_split(X, y, test_size=test_size, random_state=random_state, stratify=y)


def _tuple_rows(frame: pd.DataFrame) -> set[tuple]:
    return {tuple(row) for row in frame.itertuples(index=False, name=None)}


def main() -> None:
    raw, data = load_dataset()
    provenance = load_provenance()

    duplicates = len(raw) - len(data)
    print(f"Rows         : {len(raw)} shipped, {len(data)} distinct ({duplicates} exact duplicates dropped)")
    assert not data.duplicated().any(), "duplicate feature vectors survived de-duplication"

    polarity = validate_polarity(data)
    print(
        "Polarity     : thalach "
        f"{polarity['thalach']['disease']:.0f} vs {polarity['thalach']['healthy']:.0f}, "
        f"oldpeak {polarity['oldpeak']['disease']:.1f} vs {polarity['oldpeak']['healthy']:.1f}"
    )

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
    # The earlier single "disease-like" profile had normal thal (3) and
    # non-anginal pain (cp 3), so it was mixed-signal; the leaky model scored it
    # 0.89 and the honest one 0.55. These two are unambiguous: one exertional
    # angina with a reversible defect, one asymptomatic with three affected
    # vessels. Both are clinically coherent, and neither is tuned to the model.
    feature_names = list(X_train.columns)
    disease_profiles = {
        "typical angina": [68, 1, 1, 150, 250, 1, 2, 110, 1, 2.8, 2, 2, 7],
        "asymptomatic, 3 vessels": [67, 1, 4, 160, 286, 0, 2, 108, 1, 1.5, 2, 3, 3],
    }
    probs = {
        label: float(model.predict_proba(pd.DataFrame([row], columns=feature_names))[0][1])
        for label, row in disease_profiles.items()
    }
    p_hea = model.predict_proba(
        pd.DataFrame([[45, 0, 0, 120, 200, 0, 0, 172, 0, 0.0, 2, 0, 1]], columns=feature_names)
    )[0][1]
    print(
        "Sanity       : "
        + " | ".join(f"{label} P(disease)={value:.2f}" for label, value in probs.items())
        + f" | healthy-like P(disease)={p_hea:.2f}"
    )
    for label, value in probs.items():
        assert value > 0.7, f"{label} must score high - label polarity regression!"
    assert p_hea < 0.3, "HEALTHY-like profile must score low - label polarity regression!"

    # --- Persist model + metadata ----------------------------------------------
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)

    meta = {
        "name": "PulseIQ heart-disease screening model",
        "algorithm": "RandomForestClassifier(n_estimators=300, random_state=42)",
        "trained_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "sklearn_version": __import__("sklearn").__version__,
        "dataset": provenance.get("name", "data/heart.csv"),
        "dataset_rows": len(raw),
        "dataset_unique_rows": len(data),
        "dataset_duplicate_rows": duplicates,
        "dataset_sha256": hashlib.sha256(DATA_PATH.read_bytes()).hexdigest(),
        "dataset_source": {
            "name": provenance.get("name"),
            "url": provenance.get("url"),
            "doi": provenance.get("doi"),
            "licence": provenance.get("licence", "unverified"),
            "licence_url": provenance.get("licence_url"),
            "citation": provenance.get("citation"),
            "retrieved": provenance.get("retrieved"),
            "member_sha256": provenance.get("member_sha256"),
            "dropped_incomplete_rows": provenance.get("dropped_incomplete_rows"),
            "transformations": provenance.get("transformations", []),
        },
        "split": _SPLIT_RULE,
        "n_train": len(X_train),
        "n_test": len(X_test),
        "target_encoding": provenance.get(
            "target_encoding", "1 = disease, 0 = no disease"
        ),
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
            "Metrics come from distinct rows only. Earlier revisions trained on a Kaggle copy "
            "that had 723 duplicate rows in 1,025 and an inverted target, and reported ROC-AUC "
            "and recall of 1.000; that figure is withdrawn, not reproduced here. This run uses "
            "the UCI Cleveland original (CC BY 4.0) with 6 incomplete records dropped. "
            "Calibration (Brier, ECE) is measured on out-of-fold predictions, one per distinct "
            "patient."
        ),
    }
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print("Saved models/heart_model.pkl + models/heart_model_meta.json")


if __name__ == "__main__":
    main()
