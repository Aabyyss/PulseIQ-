from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.orchestrator import run_diagnosis_from_text
from backend.ai_assistant import (
    analyze_report_image,
    generate_ai_insights,
    generate_final_report_plan,
    get_active_provider,
)
from backend.realtime_service import process_live_transcript_entry

app = FastAPI(title="PulseIQ API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {
        "name": "PulseIQ API",
        "version": "2.0.0",
        "status": "ok",
        "ai_provider": get_active_provider(),
    }


@app.get("/health")
def health():
    """Health check used by the frontend to probe backend + AI provider."""
    return {
        "status": "ok",
        "ai_provider": get_active_provider(),
        "message": "All core features work with zero configuration.",
    }

@app.post("/diagnose")
def diagnose(data: dict):
    text = (data or {}).get("text", "")
    if not isinstance(text, str) or not text.strip():
        return {"error": "text is required"}

    result = run_diagnosis_from_text(text)

    return result


@app.post("/ai-insights")
def ai_insights(data: dict):
    text = (data or {}).get("text", "")
    if not isinstance(text, str) or not text.strip():
        return {"error": "text is required"}

    diagnosis = run_diagnosis_from_text(text)

    try:
        insights = generate_ai_insights(text=text, diagnosis=diagnosis)
    except RuntimeError as exc:
        return {"error": str(exc)}

    return {"diagnosis": diagnosis, "insights": insights, "ai_provider": get_active_provider()}


@app.get("/research-agents")
def research_agents():
    return {
        "agents": [
            {
                "name": "Uncertainty Quantification Agent",
                "focus": "Model calibration, confidence bounds, and uncertainty-aware triage."
            },
            {
                "name": "Causal Inference Agent",
                "focus": "Counterfactual analysis on symptom trajectories and risk factors."
            },
            {
                "name": "Multimodal Fusion Agent",
                "focus": "Fusion of voice, transcript, vitals, ECG and imaging features."
            },
            {
                "name": "Clinical Guidelines Agent",
                "focus": "Rule-grounded checks against ACC/AHA pathways and red-flag criteria."
            },
            {
                "name": "Knowledge Graph Agent",
                "focus": "Entity linking to UMLS/SNOMED and relation-aware reasoning."
            },
            {
                "name": "Evidence Retrieval Agent",
                "focus": "RAG over PubMed and guideline corpora with citation-aware outputs."
            },
            {
                "name": "Fairness & Bias Audit Agent",
                "focus": "Subgroup performance drift and fairness parity monitoring."
            },
            {
                "name": "Explainability Agent v2",
                "focus": "SHAP + temporal narrative explanations + clinician-readable rationale."
            },
            {
                "name": "Adversarial Robustness Agent",
                "focus": "Stress-testing ASR noise, paraphrase shifts, and prompt perturbations."
            },
            {
                "name": "Human Feedback Learning Agent",
                "focus": "Incorporating physician corrections into iterative policy updates."
            },
        ]
    }


@app.post("/final-report")
def final_report(data: dict):
    payload = data or {}
    try:
        report = generate_final_report_plan(payload=payload)
        report.pop("_recommended_tests", None)
    except RuntimeError as exc:
        return {"error": str(exc)}
    return {"report": report}


@app.post("/analyze-report-image")
def analyze_uploaded_report(data: dict):
    payload = data or {}
    base64_image = payload.get("image_base64", "")
    mime_type = payload.get("mime_type", "image/png")
    if not isinstance(base64_image, str) or not base64_image.strip():
        return {"error": "image_base64 is required"}
    if not isinstance(mime_type, str) or not mime_type.strip():
        mime_type = "image/png"
    try:
        result = analyze_report_image(base64_image=base64_image, mime_type=mime_type)
    except RuntimeError as exc:
        return {"error": str(exc)}
    return {"analysis": result, "ai_provider": get_active_provider()}


@app.websocket("/ws/consultation")
async def consultation_socket(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            message = await websocket.receive_json()
            speaker = message.get("speaker", "patient")
            text = message.get("text", "")
            report_text = message.get("report_text", "")
            language_code = message.get("language_code", "en-US")
            if not isinstance(text, str) or not text.strip():
                await websocket.send_json({"error": "text is required"})
                continue
            if not isinstance(report_text, str):
                report_text = ""
            if not isinstance(language_code, str) or not language_code.strip():
                language_code = "en-US"
            processed = process_live_transcript_entry(
                text=text, speaker=speaker, report_text=report_text, language_code=language_code
            )
            await websocket.send_json(processed)
    except WebSocketDisconnect:
        return
