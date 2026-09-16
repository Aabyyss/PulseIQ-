from __future__ import annotations


def evaluation_snapshot(probability: float, risk_level: str) -> dict:
    return {
        "latency_ms_target": 1500,
        "current_risk_level": risk_level,
        "predicted_probability": round(float(probability), 4),
        "quality_flags": [
            "Needs prospective validation",
            "Needs clinician adjudication dataset",
        ],
    }
