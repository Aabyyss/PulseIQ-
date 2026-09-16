from __future__ import annotations


def fairness_snapshot() -> dict:
    return {
        "status": "baseline_only",
        "note": "Subgroup fairness metrics require labeled cohort evaluation pipeline.",
        "required_fields": ["age_group", "sex", "comorbidity_profile", "outcome_label"],
    }
