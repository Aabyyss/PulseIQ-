from __future__ import annotations

from agents.doctor_copilot_agent import recommend_for_patient, suggest_next_questions
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
from agents.robustness_agent import robustness_checks
from agents.uncertainty_agent import estimate_prediction_uncertainty
from backend.ai_assistant import generate_ai_copilot_plan, translate_to_english
from backend.orchestrator import run_diagnosis_from_text


def process_live_transcript_entry(text: str, speaker: str, report_text: str = "", language_code: str = "en-US") -> dict:
    normalized_speaker = "doctor" if speaker == "doctor" else "patient"
    original_transcript = text
    english_transcript = translate_to_english(text=text, language_hint=language_code)

    symptoms = extract_symptoms_from_text(english_transcript)
    diagnosis = run_diagnosis_from_text(english_transcript) if symptoms else None
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

    return {
        "speaker": normalized_speaker,
        "transcript": english_transcript,
        "original_transcript": original_transcript,
        "language_code": language_code,
        "report_text": report_text,
        "symptoms": symptoms,
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
