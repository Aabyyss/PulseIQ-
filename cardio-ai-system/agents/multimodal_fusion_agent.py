from __future__ import annotations


def fuse_modalities(symptoms: list[str], report_text: str, risk_level: str) -> dict:
    report_lower = report_text.lower()
    modality_signals = {
        "symptom_signal_strength": len(symptoms),
        "report_has_troponin": "troponin" in report_lower,
        "report_has_ecg_change": "st elevation" in report_lower or "st depression" in report_lower,
        "model_risk_level": risk_level,
    }
    return modality_signals
