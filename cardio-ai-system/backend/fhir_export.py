"""FHIR R4 export: the structured findings as an EHR-shaped JSON Bundle.

Why this exists
---------------
Every other output in PulseIQ is a dead end: a PDF for a human, a SOAP note on
screen, a saved visit only this app can read. The competitive assessment named
the zero-cost step that changes that — *"FHIR JSON export (Condition /
Observation / DocumentReference resources) so the data is EHR-shaped and
demonstrable without a hospital system."* This module is that step: the same
structured findings the workspace already produces, written as a FHIR R4
``Bundle`` a clinician can hand to an EHR or a demo can inspect.

Design
------
- **Deterministic, offline, nothing stored.** The bundle is derived from the
  payload and the existing rule-grounded modules (condition vocabulary,
  unit-aware lab parser, entity extraction, medication safety review). No LLM,
  no network, no database write, no new dependency.
- **Only curated codes are emitted.** The one terminological source in this
  codebase is ``agents/knowledge_graph_agent`` (SNOMED + UMLS for the nine
  symptom concepts), so symptom Conditions carry those SNOMED codings.
  Everything else is text-first: a ``CodeableConcept`` with ``text`` and no
  invented ``coding``. Guessing a SNOMED/ICD-10 code for hypertension from
  memory would silently mis-code a problem list — the plausible-but-wrong
  failure this project is built to avoid (ADR-016/017).
- **Decision support stays visible.** Everything this module infers rather than
  observes is marked as such: symptoms are ``provisional`` Conditions noted as
  reported (not diagnosed), history is ``unconfirmed``, the risk band is a
  ``survey`` Observation whose code says decision-support, and the medication
  safety findings become ``DetectedIssue`` resources with their severity and
  mitigation. A clinician reviewing the bundle can tell what was measured from
  what was suggested.
- **Gaps are reported, not filled.** ``missing_information`` lists what the
  export could not represent (no age, no allergy list, no laboratory values,
  text-only conditions) instead of inventing values, and ``caveats`` states the
  one derived field (a birth year inferred from a recorded age).

Usage::

    from backend.fhir_export import build_fhir_bundle

    result = build_fhir_bundle({"text": "…", "conditions": ["hypertension"]})
    bundle = result["bundle"]

Exposed unchanged to the UI by ``POST /fhir-export`` (auth-gated, stateless).
"""

from __future__ import annotations

import base64
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any

from agents.knowledge_graph_agent import SYMPTOM_TO_ENTITIES
from agents.pharmacology_agent import detect_conditions, review_medications
from backend.encounter_context import build_medication_context
from backend.lab_report import screen_report_text
from backend.medical_entities import build_soap_note

FHIR_VERSION = "4.0.1"
SNOMED_SYSTEM = "http://snomed.info/sct"
UMLS_SYSTEM = "http://terminology.hl7.org/CodeSystem/umls"

_CLINICAL_STATUS = "http://terminology.hl7.org/CodeSystem/condition-clinical"
_VER_STATUS = "http://terminology.hl7.org/CodeSystem/condition-ver-status"
_CONDITION_CATEGORY = "http://terminology.hl7.org/CodeSystem/condition-category"
_OBSERVATION_CATEGORY = "http://terminology.hl7.org/CodeSystem/observation-category"
_INTERPRETATION = "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation"
_ACT_CODE = "http://terminology.hl7.org/CodeSystem/v3-ActCode"

_EXPORT_NOTE = (
    "Decision-support export from PulseIQ. Resources are unconfirmed and must be reviewed by a "
    "clinician before being filed in an EHR."
)

# Tags the condition vocabulary can produce -> the plain-English problem label an
# EHR problem list expects. The tag set is fixed by CONDITION_PATTERNS; an
# unrecognised value falls back to its own text, so nothing is invented.
_CONDITION_LABELS: dict[str, str] = {
    "prior_mi": "Previous myocardial infarction",
    "prior_pci_cabg": "Previous PCI or CABG",
    "established_cad": "Established coronary artery disease",
    "heart_failure": "Heart failure",
    "atrial_fibrillation": "Atrial fibrillation",
    "hypertension": "Hypertension",
    "diabetes": "Diabetes mellitus",
    "chronic_kidney_disease": "Chronic kidney disease",
    "obstructive_airway_disease": "Obstructive airway disease (asthma/COPD)",
    "peptic_ulcer": "Peptic ulcer disease or gastrointestinal bleeding",
    "bleeding_risk": "Bleeding risk or coagulopathy",
    "cerebrovascular_disease": "Cerebrovascular disease (stroke/TIA)",
    "pregnancy": "Pregnancy or breastfeeding",
    "bradyarrhythmia": "Bradyarrhythmia or heart block",
    "aortic_stenosis": "Aortic stenosis",
    "dyslipidemia": "Dyslipidaemia",
    "gout": "Gout",
    "liver_disease": "Liver disease",
    "migraine_aura": "Migraine with aura",
    "smoking": "Smoking",
    "obesity": "Obesity",
}

# Report severity -> FHIR ObservationInterpretation.
_INTERPRETATION_CODES = {
    "critical_high": ("HH", "Critical high"),
    "critical_low": ("LL", "Critical low"),
    "high": ("H", "High"),
    "low": ("L", "Low"),
    "normal": ("N", "Normal"),
}

_GENDER_MAP = {
    "m": "male", "male": "male", "man": "male", "boy": "male",
    "f": "female", "female": "female", "woman": "female", "girl": "female",
}
# Values a clinician types to mean "nothing to declare" — never an allergy record.
_NO_ALLERGY = re.compile(r"^\s*(?:none|nil|n/?k?d?a|no known|no known allergies|no allergies|unknown)\b", re.I)


def _new_id() -> str:
    return str(uuid.uuid4())


def _entry(resource: dict[str, Any]) -> dict[str, Any]:
    return {"fullUrl": f"urn:uuid:{resource['id']}", "resource": resource}


def _ref(resource_or_id: Any) -> dict[str, str]:
    """Reference a resource by the same urn used in the bundle's fullUrl."""
    resource_id = resource_or_id["id"] if isinstance(resource_or_id, dict) else str(resource_or_id)
    return {"reference": f"urn:uuid:{resource_id}"}


def _text_concept(text: str, coding: list[dict[str, str]] | None = None) -> dict[str, Any]:
    concept: dict[str, Any] = {"text": text}
    if coding:
        concept["coding"] = coding
    return concept


def _iso_date(value: Any, fallback: str) -> str:
    raw = str(value or "").strip()
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", raw)
    return match.group(1) if match else fallback


def _iso_datetime(value: Any, fallback: str) -> str:
    raw = str(value or "").strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}T", raw):
        return raw
    return f"{_iso_date(raw, fallback)}T00:00:00Z"


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [value]
    elif isinstance(value, (list, tuple, set)):
        parts = [str(item) for item in value]
    else:
        parts = [str(value)]
    out: list[str] = []
    for part in parts:
        cleaned = " ".join(part.split())
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out


def _review_context(payload: dict[str, Any], narrative: str, report_text: str) -> tuple[dict[str, Any], dict[str, Any]]:
    patient = {
        "age": payload.get("patient_age", payload.get("age")),
        "sex": payload.get("patient_gender", payload.get("sex")),
        "conditions": payload.get("conditions"),
        "allergies": payload.get("allergies"),
        "current_medications": payload.get("current_medications"),
        "labs": payload.get("labs") if isinstance(payload.get("labs"), dict) else None,
        "pregnancy": payload.get("pregnancy") if isinstance(payload.get("pregnancy"), bool) else None,
    }
    symptoms = _string_list(payload.get("symptom_notes")) + _string_list(payload.get("symptoms"))
    context = build_medication_context(narrative, report_text, patient, symptoms)
    return patient, context


def build_fhir_bundle(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Turn one encounter's structured findings into a FHIR R4 Bundle.

    Returns ``{bundle, resource_counts, missing_information, caveats, disclaimer}``.
    The bundle is a ``collection`` of Patient, Encounter, Condition(s),
    Observation(s), AllergyIntolerance(s), MedicationStatement(s),
    DetectedIssue(s) and a DocumentReference holding the consultation document.
    """
    data = payload if isinstance(payload, dict) else {}
    narrative = "\n".join(
        part for part in (str(data.get("text") or ""), str(data.get("report_text") or "")) if part.strip()
    ).strip()
    report_text = str(data.get("report_text") or "").strip()
    today = date.today().isoformat()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    visit_date = _iso_date(visit_date_raw := data.get("visit_date"), today)

    patient_form, context = _review_context(data, narrative, report_text)
    symptoms = _string_list(context.get("symptoms"))
    conditions = _string_list(context.get("conditions"))
    allergies = _string_list(context.get("allergies"))
    current_medications = _string_list(context.get("current_medications"))
    labs = screen_report_text(report_text).get("values", []) if report_text else []

    missing: list[str] = []
    caveats: list[str] = []

    # ---------------------------------------------------------------- Patient
    patient: dict[str, Any] = {
        "resourceType": "Patient",
        "id": _new_id(),
    }
    name = str(data.get("patient_name") or "").strip()
    if name:
        patient["name"] = [{"text": name}]
    gender = _GENDER_MAP.get(str(patient_form.get("sex") or "").strip().lower())
    patient["gender"] = gender or "unknown"
    if not gender and patient_form.get("sex"):
        caveats.append(f"Patient gender '{patient_form['sex']}' is not an administrative-gender value; exported as 'unknown'.")
    age = context.get("age")
    if isinstance(age, int) and 0 < age < 130:
        # FHIR allows a year-only partial date; an age alone implies a birth year.
        patient["birthDate"] = f"{datetime.now(timezone.utc).year - age}"
        caveats.append(
            f"Patient.birthDate is the year derived from the recorded age ({age}) — accurate to about "
            "±1 year, not a recorded date of birth."
        )
    else:
        missing.append("No age recorded — birthDate is omitted rather than guessed.")
    if not name:
        missing.append("No patient name recorded — the export carries no filing label.")
    patient["meta"] = {"tag": [{"system": "urn:pulseiq:source", "code": "pulseiq-export", "display": "PulseIQ FHIR export"}]}

    encounter = {
        "resourceType": "Encounter",
        "id": _new_id(),
        "meta": patient["meta"],
        "status": "finished",
        "class": {"system": _ACT_CODE, "code": "AMB", "display": "ambulatory"},
        "subject": _ref(patient),
        "period": {"start": _iso_datetime(visit_date_raw, today)},
    }
    complaint = str(data.get("chief_complaint") or "").strip()
    if complaint:
        encounter["reasonCode"] = [_text_concept(complaint)]
    doctor = str(data.get("doctor_name") or "").strip()
    if doctor:
        practitioner = {
            "resourceType": "Practitioner",
            "id": _new_id(),
            "meta": patient["meta"],
            "name": [{"text": doctor}],
        }
        encounter["participant"] = [{"individual": _ref(practitioner)}]
    else:
        practitioner = None

    conditions_resources: list[dict[str, Any]] = []
    for symptom in symptoms:
        codings: list[dict[str, str]] = []
        for tag in SYMPTOM_TO_ENTITIES.get(symptom, []):
            prefix, _, code = tag.partition(":")
            if prefix == "SNOMED" and code:
                codings.append({"system": SNOMED_SYSTEM, "code": code, "display": symptom})
            elif prefix == "UMLS" and code:
                codings.append({"system": UMLS_SYSTEM, "code": code, "display": symptom})
        conditions_resources.append({
            "resourceType": "Condition",
            "id": _new_id(),
            "meta": patient["meta"],
            "clinicalStatus": {"coding": [{"system": _CLINICAL_STATUS, "code": "active"}]},
            "verificationStatus": {"coding": [{"system": _VER_STATUS, "code": "provisional"}]},
            "category": [{"coding": [{"system": _CONDITION_CATEGORY, "code": "problem-list-item"}]}],
            "code": _text_concept(symptom, codings),
            "subject": _ref(patient),
            "encounter": _ref(encounter),
            "recordedDate": now,
            "note": [{"text": "Reported during this encounter — a symptom to evaluate, not a diagnosis."}],
        })
    # History entries that the condition vocabulary recognises become exactly one
    # problem per canonical tag (so "prior MI" and "stent 2023" cannot produce the
    # same problem twice); anything it does not recognise is exported as written.
    tagged: list[str] = []
    history: list[tuple[str, bool]] = []  # (label, came_from_a_tag)
    for entry in conditions:
        tags = detect_conditions([entry])
        if tags:
            for tag in tags:
                if tag not in tagged:
                    tagged.append(tag)
        elif entry:
            history.append((entry, False))
    history.extend((_CONDITION_LABELS.get(tag, tag), True) for tag in tagged)
    for label, _from_tag in history:
        conditions_resources.append({
            "resourceType": "Condition",
            "id": _new_id(),
            "meta": patient["meta"],
            "clinicalStatus": {"coding": [{"system": _CLINICAL_STATUS, "code": "active"}]},
            "verificationStatus": {"coding": [{"system": _VER_STATUS, "code": "unconfirmed"}]},
            "category": [{"coding": [{"system": _CONDITION_CATEGORY, "code": "problem-list-item"}]}],
            "code": _text_concept(label),
            "subject": _ref(patient),
            "encounter": _ref(encounter),
            "recordedDate": now,
            "note": [{"text": "Recorded in the visit history by the clinician; no coded terminology is asserted."}],
        })

    observations: list[dict[str, Any]] = []
    for value in labs:
        interpretation = _INTERPRETATION_CODES.get(str(value.get("status") or "").lower())
        observation: dict[str, Any] = {
            "resourceType": "Observation",
            "id": _new_id(),
            "meta": patient["meta"],
            "status": "final",
            "category": [{"coding": [{"system": _OBSERVATION_CATEGORY, "code": "laboratory"}]}],
            "code": _text_concept(str(value.get("name") or value.get("key") or "Laboratory value")),
            "subject": _ref(patient),
            "encounter": _ref(encounter),
            "effectiveDateTime": _iso_datetime(visit_date_raw, today),
        }
        number = value.get("value")
        unit = str(value.get("unit") or "").strip()
        if number is not None:
            quantity: dict[str, Any] = {"value": number}
            if unit:
                # Unit text only: mapping these strings onto UCUM codes would be a
                # guess, and a wrong UCUM code is worse than no code.
                quantity["unit"] = unit
            observation["valueQuantity"] = quantity
        if value.get("reference"):
            observation["referenceRange"] = [{"text": str(value["reference"])}]
        if interpretation:
            observation["interpretation"] = [{"coding": [{
                "system": _INTERPRETATION,
                "code": interpretation[0],
                "display": interpretation[1],
            }]}]
        note = " ".join(part for part in (str(value.get("explanation") or ""), str(value.get("note") or "")) if part).strip()
        if note:
            observation["note"] = [{"text": note}]
        observations.append(observation)

    risk_level = str(data.get("risk_level") or "").strip()
    if risk_level:
        observations.append({
            "resourceType": "Observation",
            "id": _new_id(),
            "meta": patient["meta"],
            "status": "final",
            "category": [{"coding": [{"system": _OBSERVATION_CATEGORY, "code": "survey"}]}],
            "code": _text_concept("Cardiac screening risk band (decision-support output)"),
            "subject": _ref(patient),
            "encounter": _ref(encounter),
            "effectiveDateTime": _iso_datetime(visit_date_raw, today),
            "valueString": risk_level,
            "note": [{"text": "Screening estimate from the captured narrative — not a diagnosis and not a validated score."}],
        })

    allergy_resources: list[dict[str, Any]] = []
    declared = [term for term in allergies if not _NO_ALLERGY.match(term)]
    for term in declared:
        allergy_resources.append({
            "resourceType": "AllergyIntolerance",
            "id": _new_id(),
            "meta": patient["meta"],
            "clinicalStatus": {"coding": [{"system": _CLINICAL_STATUS, "code": "active"}]},
            "verificationStatus": {"coding": [{"system": _VER_STATUS, "code": "unconfirmed"}]},
            "type": "allergy",
            "category": ["medication"],
            "criticality": "unable-to-assess",
            "code": _text_concept(term),
            "patient": _ref(patient),
            "encounter": _ref(encounter),
            "recordedDate": now,
        })
    if not declared:
        missing.append("No drug allergy recorded — allergy screening could not be represented.")

    medication_resources: list[dict[str, Any]] = []
    for medication in current_medications:
        medication_resources.append({
            "resourceType": "MedicationStatement",
            "id": _new_id(),
            "meta": patient["meta"],
            "status": "active",
            "medicationCodeableConcept": _text_concept(medication),
            "subject": _ref(patient),
            "context": _ref(encounter),
            "effectiveDateTime": _iso_datetime(visit_date_raw, today),
        })
    if not current_medications:
        missing.append("No current medications recorded — the medication list is not represented.")

    # ------------------------------------------------- medication safety review
    review = review_medications(
        symptoms=symptoms,
        conditions=conditions,
        allergies=allergies,
        current_medications=current_medications,
        age=context.get("age"),
        sex=context.get("sex"),
        risk_level=risk_level if risk_level in ("Low", "Medium", "High") else None,
        labs=context.get("labs") or {},
        pregnancy=context.get("pregnancy"),
    )
    issues: list[dict[str, Any]] = []

    def _issue(code: str, severity: str, detail: str, terms: list[str], mitigation: str = "") -> dict[str, Any]:
        issue: dict[str, Any] = {
            "resourceType": "DetectedIssue",
            "id": _new_id(),
            "meta": patient["meta"],
            "status": "preliminary",
            "code": _text_concept(code),
            "severity": severity,
            "patient": _ref(patient),
            "identifiedDateTime": now,
            "detail": detail,
        }
        if terms:
            issue["implicated"] = [{"display": term} for term in terms if term]
        if mitigation:
            issue["mitigation"] = [{"action": {"text": mitigation}}]
        return issue

    for alert in review.get("allergy_alerts") or []:
        _severity = "high"
        issues.append(_issue(
            "Allergy conflict",
            _severity,
            f"Reported allergy matches {alert.get('drug')} ({', '.join(alert.get('matched_terms') or [])}) — do not use.",
            [str(alert.get("drug") or "")],
            str(alert.get("alternative") or ""),
        ))
    for block in review.get("contraindicated") or []:
        reasons = [str(item.get("note") or "") for item in (block.get("blocks") or []) if item.get("note")]
        issues.append(_issue(
            "Contraindication or review-before-use flag",
            "high" if block.get("severity") == "absolute" else "moderate",
            " ".join(reasons) or str(block.get("note") or ""),
            [str(block.get("drug") or "")],
            "Already documented — review and consider stopping with the prescriber." if block.get("already_documented") else "",
        ))
    for alert in review.get("interaction_alerts") or []:
        issues.append(_issue(
            "Drug interaction",
            "high" if alert.get("severity") == "major" else "moderate",
            str(alert.get("note") or ""),
            [str(drug) for drug in (alert.get("drugs") or [])],
            str(alert.get("action") or ""),
        ))

    # -------------------------------------------------------- consultation doc
    report = data.get("report") if isinstance(data.get("report"), dict) else None
    document_lines: list[str] = []
    if report:
        document_lines.append(str(report.get("title") or "Consultation report"))
        if report.get("summary"):
            document_lines.append(f"\nSummary: {report['summary']}")
        for heading, key in (
            ("Probable diagnosis", "probable_diagnosis"),
            ("Doctor advice", "doctor_advice"),
            ("Medical treatment plan", "medical_treatment_plan"),
            ("Follow-up plan", "follow_up_plan"),
            ("Red flags", "red_flags"),
        ):
            items = _string_list(report.get(key))
            if items:
                document_lines.append(f"\n{heading}:")
                document_lines.extend(f"- {item}" for item in items)
    else:
        note = build_soap_note(transcript=narrative, symptoms=symptoms, report_text=report_text, risk_level=risk_level or "Low")
        document_lines.append("Structured consultation note (deterministic SOAP form)")
        for heading, key in (
            ("Subjective", "subjective"),
            ("Objective", "objective"),
            ("Assessment", "assessment"),
            ("Plan", "plan"),
        ):
            items = _string_list(note.get(key))
            if items:
                document_lines.append(f"\n{heading}:")
                document_lines.extend(f"- {item}" for item in items)
        document_lines.append(f"\n{note.get('note', '')}".rstrip())
    document_text = "\n".join(document_lines).strip()
    document = {
        "resourceType": "DocumentReference",
        "id": _new_id(),
        "meta": patient["meta"],
        "status": "current",
        "docStatus": "preliminary",
        "type": _text_concept("Cardiology consultation note"),
        "subject": _ref(patient),
        "context": {"encounter": [_ref(encounter)], "period": {"start": _iso_datetime(visit_date_raw, today)}},
        "date": now,
        "description": "Consultation findings exported from PulseIQ for clinician review.",
        "content": [{"attachment": {
            "contentType": "text/plain; charset=utf-8",
            "title": "consultation-note.txt",
            "size": len(document_text.encode("utf-8")),
            "data": base64.b64encode(document_text.encode("utf-8")).decode("ascii"),
        }}],
    }

    if not narrative:
        missing.append("No narrative text supplied — Conditions and Observations come from the visit form only.")
    if not report_text:
        missing.append("No laboratory or report text supplied — no laboratory Observations were produced.")
    if any(not from_tag for _label, from_tag in history):
        missing.append(
            "At least one history entry is exported as free text: this codebase has no curated SNOMED/ICD-10 "
            "table for condition phrasing, and a guessed code would mis-code the problem list."
        )
    if any(SYMPTOM_TO_ENTITIES.get(symptom) for symptom in symptoms):
        caveats.append("Symptom codings use the SNOMED/UMLS map already curated in agents/knowledge_graph_agent.py.")

    resources: list[dict[str, Any]] = [patient]
    if practitioner:
        resources.append(practitioner)
    resources.append(encounter)
    resources.extend(conditions_resources)
    resources.extend(observations)
    resources.extend(allergy_resources)
    resources.extend(medication_resources)
    resources.extend(issues)
    resources.append(document)

    bundle = {
        "resourceType": "Bundle",
        "id": _new_id(),
        "meta": {
            "lastUpdated": now,
            "tag": [{"system": "urn:pulseiq:source", "code": "pulseiq-export", "display": "PulseIQ FHIR export"}],
        },
        "type": "collection",
        "timestamp": now,
        "entry": [_entry(resource) for resource in resources],
    }

    counts: dict[str, int] = {}
    for resource in resources:
        counts[resource["resourceType"]] = counts.get(resource["resourceType"], 0) + 1

    return {
        "bundle": bundle,
        "fhir_version": FHIR_VERSION,
        "resource_counts": counts,
        "missing_information": missing,
        "caveats": caveats,
        "medication_summary": review.get("summary", ""),
        "disclaimer": _EXPORT_NOTE,
    }
