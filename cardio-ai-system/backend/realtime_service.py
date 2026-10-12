from __future__ import annotations

from agents.doctor_copilot_agent import recommend_for_patient, suggest_next_questions
from agents.attribution_agent import attribute_suggestions, plan_confidence
from agents.causal_inference_agent import generate_counterfactuals
from agents.evaluation_agent import evaluation_snapshot
from agents.evidence_retrieval_agent import retrieve_evidence_snippets
from agents.fairness_bias_agent import fairness_snapshot
from agents.guidelines_agent import check_guideline_alignment
from agents.heart_region_agent import infer_cardiac_regions
from agents.human_feedback_agent import record_feedback_stub
from agents.knowledge_graph_agent import link_medical_entities
from agents.multimodal_fusion_agent import fuse_modalities
from agents.nlp_symptom_agent import extract_symptoms_from_text
from agents.pain_mapper_agent import map_symptoms_to_pain_points
from agents.pharmacology_agent import review_medications
from agents.robustness_agent import robustness_checks
from agents.uncertainty_agent import estimate_prediction_uncertainty
from backend.ai_assistant import generate_ai_copilot_plan, translate_to_english
from backend.encounter_context import build_medication_context
from backend.risk_score_context import build_risk_scores
from backend.medical_entities import extract_entities
from backend.orchestrator import run_diagnosis_from_text
from backend import vocabulary_service


def medication_review_for_encounter(
    encounter_text: str,
    report_text: str = "",
    patient: dict | None = None,
    symptoms: list[str] | None = None,
    risk_level: str | None = None,
    risk_scores: dict | None = None,
) -> dict:
    """Medication review for a live encounter, accumulated across its lines.

    ``encounter_text`` is everything said so far (the API layer supplies the
    already-translated lines plus the current one), so each spoken line can
    change the options, blocks and interactions without the caller keeping any
    pharmacology state itself. ``patient`` carries the visit details the
    clinician recorded — age, sex, conditions/history, allergies, current
    medications and optionally pregnancy. The union rules live in
    :mod:`backend.encounter_context`, shared with ``POST /medication-review``,
    so the page and the live screen judge the same patient identically.

    Nothing is stored; the review is recomputed from the encounter every time.
    """
    context = build_medication_context(encounter_text, report_text, patient, symptoms)
    recorded_risk = patient.get("risk_level") if isinstance(patient, dict) else None
    scores = risk_scores if risk_scores is not None else build_risk_scores(
        encounter_text, report_text, patient, context["symptoms"]
    )

    review = review_medications(
        symptoms=context["symptoms"],
        conditions=context["conditions"],
        allergies=context["allergies"],
        current_medications=context["current_medications"],
        age=context["age"],
        sex=context["sex"],
        risk_level=risk_level if risk_level in ("Low", "Medium", "High") else recorded_risk,
        labs=context["labs"],
        pregnancy=context["pregnancy"],
        risk_scores=scores,
    )
    review["extracted"] = {
        "entities": context["entities"],
        "allergies_from_text": context["allergies_from_text"],
        "labs_used": context["labs"],
    }
    return review


def medication_review_for_live_line(
    text: str,
    transcript: str = "",
    report_text: str = "",
    patient: dict | None = None,
    symptoms: list[str] | None = None,
) -> dict:
    """The safety screen as it stands the moment a line is recognised.

    The full copilot plan calls the local model and can take tens of seconds on
    CPU (ADR-018's ``analysis`` frame), but the medication screen needs no model
    at all: it is deterministic rules over text that is already in hand. So the
    socket handler computes this from the line as spoken — plus everything said
    before it and the visit details — and ships it on the instant ``line_ack``
    frame, while the analysis frame rebuilds the same review afterwards with the
    diagnosis band and the English translation folded in.

    Differences from the analysis frame, both deliberate: the current line is
    the original wording (allergy/condition/medication patterns are English-keyed,
    so a non-English line can gain findings once translated), and ``risk_level``
    is unset because the band is not known yet — the pathway still escalates on
    the presentation itself (a suspected ACS indication is an emergency with or
    without a band), so the early screen can never soften the presentation.
    """
    encounter_text = "\n".join(
        part for part in ((transcript or "").strip(), (text or "").strip()) if part
    )
    return medication_review_for_encounter(
        encounter_text=encounter_text,
        report_text=report_text,
        patient=patient,
        symptoms=symptoms,
    )


def process_live_transcript_entry(
    text: str,
    speaker: str,
    report_text: str = "",
    language_code: str = "en-US",
    owner_id: int | None = None,
    patient: dict | None = None,
    transcript: str = "",
) -> dict:
    normalized_speaker = "doctor" if speaker == "doctor" else "patient"
    original_transcript = text
    english_transcript = translate_to_english(text=text, language_hint=language_code)
    # Everything said before this line, already translated by the caller; the
    # medication safety screen reads the whole encounter, not one line.
    encounter_text = "\n".join(
        part for part in ((transcript or "").strip(), english_transcript.strip()) if part
    )

    # The dictionary matches English and Urdu directly, so extraction runs
    # on BOTH the original and the translated text and the findings are
    # unioned: if translation degrades, hallucinates, or fails (no LLM,
    # timeout), the original-language findings survive. The translated
    # narrative stays the diagnosis input for its richer English context.
    # Both passes honour the signed-in clinician's learned vocabulary, so a
    # phrase taught this session applies from the next line onward.
    symptoms = vocabulary_service.extract_symptoms_for_user(english_transcript, owner_id)
    for symptom in vocabulary_service.extract_symptoms_for_user(original_transcript, owner_id):
        if symptom not in symptoms:
            symptoms.append(symptom)
    diagnosis = run_diagnosis_from_text(english_transcript, symptoms=symptoms) if symptoms else None
    risk_level = diagnosis["risk_level"] if diagnosis else "Low"
    probability = diagnosis["probability"] if diagnosis else 0.5
    cardiac_regions = infer_cardiac_regions(symptoms=symptoms, report_text=report_text)
    default_questions = suggest_next_questions(symptoms=symptoms, transcript=text)
    default_recommendations = recommend_for_patient(risk_level=risk_level, transcript=english_transcript)
    ai_copilot = {
        "doctor_questions": default_questions,
        "recommended_tests": [
            "12-lead ECG",
            "Serial troponin",
            "Vitals and pulse oximetry",
        ],
        "next_steps": default_recommendations,
        "diagnostic_impression": [
            "Symptom pattern requires clinical correlation with ECG and biomarkers."
        ],
        "urgency": "high" if risk_level == "High" else ("moderate" if risk_level == "Medium" else "low"),
        "safety_note": "Decision support only. Confirm with clinical exam and institutional protocol.",
    }

    if diagnosis:
        try:
            ai_copilot = generate_ai_copilot_plan(
                text=text,
                report_text=report_text,
                diagnosis=diagnosis,
                symptoms=symptoms,
            )
        except RuntimeError:
            # Keep deterministic fallback when API key/network/model output fails.
            pass

    # Hallucination guard: every suggestion gets the guideline (or plain
    # reason) that backs it, and the whole plan carries an honest confidence
    # tier — including an explicit "not enough information" state.
    confidence = plan_confidence(symptoms=symptoms, report_text=report_text, probability=probability)
    ai_copilot["suggestion_sources"] = attribute_suggestions(
        doctor_questions=ai_copilot.get("doctor_questions", []),
        recommended_tests=ai_copilot.get("recommended_tests", []),
        next_steps=ai_copilot.get("next_steps", []),
    )
    ai_copilot["confidence"] = confidence
    if confidence["insufficient_information"] == "true":
        # Say so instead of guessing: no fabricated direction, just the
        # open question that would actually resolve the gap.
        ai_copilot["diagnostic_impression"] = [
            "Not enough information yet — gather the history before forming a direction."
        ]
        ai_copilot["safety_note"] = confidence["reason"]

    # Built once per line and shared: the medication review grades its urgency
    # from it, the diagnosis payload carries it beside the model's band, and the
    # frame hands it to the UI — the three can never disagree.
    risk_scores = build_risk_scores(encounter_text, report_text, patient, symptoms)
    if diagnosis:
        diagnosis["risk_scores"] = risk_scores

    medication_review = medication_review_for_encounter(
        encounter_text=encounter_text,
        report_text=report_text,
        patient=patient,
        symptoms=symptoms,
        risk_level=risk_level,
        risk_scores=risk_scores,
    )

    return {
        "speaker": normalized_speaker,
        "transcript": english_transcript,
        "original_transcript": original_transcript,
        "language_code": language_code,
        "report_text": report_text,
        "symptoms": symptoms,
        "medical_entities": extract_entities(text),
        "medication_review": medication_review,
        "risk_scores": risk_scores,
        "diagnosis": diagnosis,
        "pain_points": map_symptoms_to_pain_points(symptoms),
        "cardiac_regions": cardiac_regions,
        "doctor_next_questions": ai_copilot["doctor_questions"],
        "patient_recommendations": ai_copilot["next_steps"],
        "ai_copilot": ai_copilot,
        "uncertainty": estimate_prediction_uncertainty(probability=probability),
        "causal_hypotheses": generate_counterfactuals(symptoms=symptoms),
        "multimodal_fusion": fuse_modalities(symptoms=symptoms, report_text=report_text, risk_level=risk_level),
        "guideline_alignment": check_guideline_alignment(symptoms=symptoms, report_text=report_text),
        "knowledge_graph_links": link_medical_entities(symptoms=symptoms),
        "evidence_snippets": retrieve_evidence_snippets(symptoms=symptoms, report_text=report_text),
        "fairness_snapshot": fairness_snapshot(),
        "robustness_checks": robustness_checks(transcript=english_transcript),
        "human_feedback_stub": record_feedback_stub(note=f"Auto-captured for speaker={normalized_speaker}"),
        "evaluation_snapshot": evaluation_snapshot(probability=probability, risk_level=risk_level),
    }
