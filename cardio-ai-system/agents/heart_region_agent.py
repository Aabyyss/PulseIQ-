from __future__ import annotations

from typing import List


def infer_cardiac_regions(symptoms: List[str], report_text: str) -> list[dict]:
    lowered = report_text.lower()
    regions: list[dict] = []

    if "chest pain" in symptoms:
        regions.append(
            {
                "region": "Anterior wall (LAD territory)",
                "likelihood": "moderate",
                "clinical_note": "Pressure-type chest pain can indicate anterior ischemic burden; correlate with ECG troponin dynamics.",
                "marker": {"x": 0.04, "y": 0.16, "z": 0.22},
            }
        )
    if "shortness of breath" in symptoms:
        regions.append(
            {
                "region": "Left ventricle (pump function)",
                "likelihood": "moderate",
                "clinical_note": "Dyspnea may reflect reduced LV performance or elevated filling pressures.",
                "marker": {"x": -0.07, "y": 0.03, "z": 0.15},
            }
        )
    if "palpitations" in symptoms:
        regions.append(
            {
                "region": "Conduction system / atrial rhythm focus",
                "likelihood": "moderate",
                "clinical_note": "Palpitations suggest arrhythmic activity; evaluate rhythm strip and electrolytes.",
                "marker": {"x": 0.1, "y": 0.27, "z": 0.1},
            }
        )

    if "st elevation inferior" in lowered or "inferior stemi" in lowered:
        regions.append(
            {
                "region": "Inferior wall (RCA territory)",
                "likelihood": "high",
                "clinical_note": "Inferior ST changes align with RCA involvement; assess RV lead extension and hemodynamics.",
                "marker": {"x": -0.02, "y": -0.08, "z": 0.2},
            }
        )
    if "st elevation anterior" in lowered or "anterior stemi" in lowered:
        regions.append(
            {
                "region": "Anterior wall / septum (LAD)",
                "likelihood": "high",
                "clinical_note": "Anterior ST changes indicate LAD territory risk and larger myocardium at stake.",
                "marker": {"x": 0.08, "y": 0.14, "z": 0.24},
            }
        )
    if "troponin" in lowered and ("positive" in lowered or "elevated" in lowered):
        regions.append(
            {
                "region": "Myocardial injury (global)",
                "likelihood": "high",
                "clinical_note": "Elevated troponin supports myocardial injury; trend values and integrate with ECG/time course.",
                "marker": {"x": 0.0, "y": 0.07, "z": 0.18},
            }
        )

    # Deduplicate by region
    unique = {}
    for region in regions:
        unique[region["region"]] = region
    return list(unique.values())[:6]
