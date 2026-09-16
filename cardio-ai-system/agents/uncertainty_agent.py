from __future__ import annotations


def estimate_prediction_uncertainty(probability: float) -> dict:
    confidence = abs(probability - 0.5) * 2
    if confidence >= 0.7:
        bucket = "high_confidence"
    elif confidence >= 0.4:
        bucket = "moderate_confidence"
    else:
        bucket = "low_confidence"
    return {"confidence_score": round(confidence, 3), "confidence_bucket": bucket}
