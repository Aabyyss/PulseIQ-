"""Evaluate the Cleveland-trained model on the other three UCI cohorts.

Why this is separate from `train_model.py`
------------------------------------------
Cleveland is the only cohort with enough complete records to train on. The other
sites are not extra training rows: they are external validation, and they arrive
with a specific kind of missingness that a single accuracy number would hide:

* Hungarian — 291 of 294 records lack `ca`, 266 lack `thal`, 190 lack `slope`;
  exactly **1** record is complete.
* Switzerland — **no complete record**, and `chol` is 0 in all 123 (a placeholder
  for "not measured", not a cholesterol of zero).
* VA Long Beach — 198 of 200 lack `ca`, 166 lack `thal`; **1** complete record.

So "report metrics per site" cannot mean complete-case evaluation: it would report
one Hungarian row and no Swiss rows. Instead each site is scored twice:

1. **all rows**, with missing features filled from the *Cleveland training split*
   only (medians for continuous fields, modes for categorical ones) — no value
   from the site being scored informs its own imputation;
2. **low imputation** (at most two filled features), to show whether the result
   depends on inventing the missing evidence.

Every per-site block also states its missingness, its prevalence and how many
values were filled, so the AUC is read next to the conditions that produced it.
The output is a table for the model card and `models/site_evaluation.json`.

Run:: 

    python -m backend.site_evaluation
"""

from __future__ import annotations

import csv
import json
import pickle
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.sklearn_compat import ensure_sklearn_importable  # noqa: E402

ensure_sklearn_importable()

from sklearn.metrics import (  # noqa: E402
    accuracy_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from backend.train_model import (  # noqa: E402
    MODEL_PATH,
    load_dataset,
    split_dataset,
)

SITES_PATH = ROOT / "data" / "heart_sites.csv"
REPORT_PATH = ROOT / "models" / "site_evaluation.json"

FEATURES = [
    "age", "sex", "cp", "trestbps", "chol", "fbs", "restecg",
    "thalach", "exang", "oldpeak", "slope", "ca", "thal",
]
CATEGORICAL = {"sex", "cp", "fbs", "restecg", "exang", "slope", "ca", "thal"}

# Values the UCI files use where a measurement is absent. `oldpeak = 0` is a real
# finding (no ST depression), so only fields where zero is impossible are here.
SENTINEL_ZEROS = {"chol", "trestbps"}

SITE_ORDER = ["cleveland", "hungarian", "switzerland", "va"]
SITE_LABELS = {
    "cleveland": "Cleveland",
    "hungarian": "Hungarian",
    "switzerland": "Switzerland",
    "va": "VA Long Beach",
}
LOW_IMPUTATION_LIMIT = 2


def load_site_rows(path: Path = SITES_PATH) -> list[dict]:
    """Parse `heart_sites.csv`, turning blanks and impossible zeros into None."""
    rows: list[dict] = []
    with open(path, newline="", encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            features: dict[str, float | None] = {}
            sentinels = 0
            for column in FEATURES:
                raw = record[column].strip()
                if raw == "":
                    features[column] = None
                    continue
                value = float(raw)
                if column in SENTINEL_ZEROS and value == 0:
                    features[column] = None
                    sentinels += 1
                else:
                    features[column] = value
            rows.append(
                {
                    "site": record["site"],
                    "features": features,
                    "target": int(record["target"]),
                    "sentinel_zeros": sentinels,
                }
            )
    return rows


def training_imputation() -> tuple[dict, int]:
    """Medians/modes of the **Cleveland training split**, and its size.

    Deliberately derived from the split the model was fitted on. Using the whole
    dataset, or the site being scored, would leak the test rows into the values
    that stand in for missing ones.
    """
    _, data = load_dataset()
    X_train = split_dataset(data)[0]
    statistics: dict[str, float] = {}
    for column in FEATURES:
        if column in CATEGORICAL:
            statistics[column] = float(X_train[column].mode().iloc[0])
        else:
            statistics[column] = float(X_train[column].median())
    return statistics, len(X_train)


def impute(features: dict, statistics: dict) -> tuple[list[float], int]:
    """Fill missing fields from the Cleveland statistics; return the count filled."""
    vector: list[float] = []
    imputed = 0
    for column in FEATURES:
        value = features[column]
        if value is None:
            vector.append(statistics[column])
            imputed += 1
        else:
            vector.append(float(value))
    return vector, imputed


def _metrics(y_true: list[int], y_prob: list[float]) -> dict:
    if not y_true:
        return {"n": 0, "metrics": None}
    y_pred = [1 if probability >= 0.5 else 0 for probability in y_prob]
    single_class = len(set(y_true)) < 2
    return {
        "n": len(y_true),
        "metrics": {
            "accuracy": float(accuracy_score(y_true, y_pred)),
            "precision": float(precision_score(y_true, y_pred, zero_division=0)),
            "recall": float(recall_score(y_true, y_pred, zero_division=0)),
            "f1": float(f1_score(y_true, y_pred, zero_division=0)),
            "roc_auc": None if single_class else float(roc_auc_score(y_true, y_prob)),
            "brier": float(brier_score_loss(y_true, y_prob)),
            "mean_predicted": sum(y_prob) / len(y_prob),
        },
        "disease_rate": sum(y_true) / len(y_true),
    }


def score_rows(rows: list[dict], model, statistics: dict, max_imputed: int | None = None) -> dict:
    """Score rows, optionally only those needing at most `max_imputed` fills."""
    vectors: list[list[float]] = []
    labels: list[int] = []
    imputed_total = 0
    for row in rows:
        vector, imputed = impute(row["features"], statistics)
        if max_imputed is not None and imputed > max_imputed:
            continue
        vectors.append(vector)
        labels.append(int(row["target"]))
        imputed_total += imputed

    if not vectors:
        return {"n": 0, "metrics": None, "imputed_values": 0}

    probabilities = model.predict_proba(pd.DataFrame(vectors, columns=FEATURES))[:, 1].tolist()
    report = _metrics(labels, probabilities)
    report["imputed_values"] = imputed_total
    report["mean_imputed_per_row"] = imputed_total / len(vectors)
    return report


def site_missingness(rows: list[dict]) -> dict:
    total = len(rows)
    missing = {
        column: sum(1 for row in rows if row["features"][column] is None)
        for column in FEATURES
    }
    per_row = [
        sum(1 for column in FEATURES if row["features"][column] is None) for row in rows
    ]
    return {
        "rows": total,
        "disease": sum(row["target"] for row in rows),
        "disease_rate": (sum(row["target"] for row in rows) / total) if total else 0.0,
        "complete_rows": sum(1 for count in per_row if count == 0),
        "mean_missing_per_row": (sum(per_row) / total) if total else 0.0,
        "missing": {
            column: {"count": count, "share": (count / total) if total else 0.0}
            for column, count in missing.items()
        },
        "sentinel_zeros": sum(row["sentinel_zeros"] for row in rows),
    }


def build_report(model, statistics: dict, training_rows: int) -> dict:
    rows = load_site_rows()
    by_site = {site: [row for row in rows if row["site"] == site] for site in SITE_ORDER}

    sites: dict[str, dict] = {}
    for site in SITE_ORDER:
        site_rows = by_site[site]
        block = site_missingness(site_rows)
        if site == "cleveland":
            # Cleveland rows were used for training, so scoring all of them would
            # be self-assessment. Its observable figure is the held-out split.
            _, data = load_dataset()
            X_test, y_test = split_dataset(data)[1], split_dataset(data)[3]
            probabilities = model.predict_proba(X_test)[:, 1].tolist()
            holdout = _metrics(y_test.tolist(), probabilities)
            holdout["imputed_values"] = 0
            holdout["mean_imputed_per_row"] = 0.0
            block["internal_holdout"] = holdout
        else:
            block["all_rows"] = score_rows(site_rows, model, statistics)
            block["low_imputation"] = score_rows(
                site_rows, model, statistics, max_imputed=LOW_IMPUTATION_LIMIT
            )
        sites[site] = block

    return {
        "model": str(MODEL_PATH.relative_to(ROOT)),
        "imputation": {
            "source": f"Cleveland training split ({training_rows} rows)",
            "values": {column: round(value, 3) for column, value in statistics.items()},
            "sentinels": "chol = 0 and trestbps = 0 are treated as missing (impossible values)",
            "low_imputation_limit": LOW_IMPUTATION_LIMIT,
        },
        "sites": sites,
    }


def format_table(report: dict) -> str:
    lines = [
        f"{'site':<13}{'rows':>5}{'complete':>9}{'disease':>9}{'AUC(all)':>10}"
        f"{'AUC(<=2)':>10}{'n(<=2)':>7}{'Brier(all)':>11}",
    ]
    for site in SITE_ORDER:
        block = report["sites"][site]
        all_rows = block.get("all_rows") or block.get("internal_holdout") or {}
        low = block.get("low_imputation") or {}
        metrics = (all_rows.get("metrics") or {})
        low_metrics = (low.get("metrics") or {})

        def show(value):
            return "-" if value is None else f"{value:.3f}"

        label = SITE_LABELS[site] + ("*" if site == "cleveland" else "")
        lines.append(
            f"{label:<13}{block['rows']:>5}{block['complete_rows']:>9}"
            f"{block['disease_rate'] * 100:>8.0f}%{show(metrics.get('roc_auc')):>10}"
            f"{show(low_metrics.get('roc_auc')):>10}{low.get('n', 0) or 0:>7}"
            f"{show(metrics.get('brier')):>11}"
        )
    lines.append("* Cleveland is the internal holdout; its rows trained the model.")
    return "\n".join(lines)


def main() -> int:
    with open(MODEL_PATH, "rb") as handle:
        model = pickle.load(handle)
    statistics, training_rows = training_imputation()
    report = build_report(model, statistics, training_rows)

    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(format_table(report))
    print(f"\nWrote {REPORT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
