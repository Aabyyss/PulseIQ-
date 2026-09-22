from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend import auth_store, rate_limit
from backend.auth import get_current_user
from backend.orchestrator import run_diagnosis_from_text
from backend.ai_assistant import (
    analyze_report_image,
    generate_ai_insights,
    generate_final_report_plan,
    get_active_provider,
)
from backend.realtime_service import process_live_transcript_entry

app = FastAPI(title="PulseIQ API", version="2.0.0")

# Reject oversized bodies (screening text and base64 images are small; a huge
# payload is a misuse/DoS attempt, not a legitimate request).
MAX_BODY_BYTES = 8 * 1024 * 1024  # 8 MB


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
        return JSONResponse(status_code=413, content={"detail": "Request body too large."})
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup_backup() -> None:
    """Snapshot the accounts/history DB at every server start (keep 10)."""
    target = auth_store.backup_database()
    if target:
        print(f"[pulseiq] database backup written: {target}")


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

# ---------------------------------------------------------------------------
# Auth — clinician accounts & sessions
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: str = Field(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$", max_length=254)
    password: str = Field(min_length=8, max_length=256)
    name: str = Field(default="", max_length=120)


class LoginRequest(BaseModel):
    email: str = Field(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$", max_length=254)
    password: str = Field(min_length=1, max_length=256)


def _session_response(user: dict, token: str) -> dict:
    return {"token": token, "user": user}


@app.post("/auth/register")
def auth_register(payload: RegisterRequest):
    try:
        user = auth_store.create_user(email=payload.email, password=payload.password, name=payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    token = auth_store.issue_token(user["id"])
    return _session_response(user, token)


def _client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


@app.post("/auth/login")
def auth_login(payload: LoginRequest, request: Request):
    remaining = rate_limit.is_locked(_client_ip(request), payload.email)
    if remaining:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {max(remaining // 60, 1)} minute(s).",
        )
    user = auth_store.verify_user(email=payload.email, password=payload.password)
    if user is None:
        rate_limit.record_failure(_client_ip(request), payload.email)
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    rate_limit.record_success(_client_ip(request), payload.email)
    token = auth_store.issue_token(user["id"])
    return _session_response(user, token)


@app.post("/auth/logout")
def auth_logout(request: Request, user: dict = Depends(get_current_user)):
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if token:
        auth_store.revoke_token(token)
    return {"ok": True}


@app.get("/auth/me")
def auth_me(user: dict = Depends(get_current_user)):
    return {"user": user}


# ---------------------------------------------------------------------------
# Per-user history — screenings & consultations (owner-scoped)
# ---------------------------------------------------------------------------

@app.post("/diagnose")
def diagnose(data: dict, user: dict = Depends(get_current_user)):
    text = (data or {}).get("text", "")
    if not isinstance(text, str) or not text.strip():
        return {"error": "text is required"}

    result = run_diagnosis_from_text(text)

    # Persist to the signed-in clinician's history (best-effort; screening
    # itself must not fail if storage hiccups).
    try:
        saved = auth_store.add_screening(user["id"], {**result, "text": text.strip()})
        result["id"] = saved["id"]
        result["createdAt"] = saved["createdAt"]
    except Exception:
        pass

    return result


@app.get("/history/screenings")
def history_screenings(user: dict = Depends(get_current_user)):
    return {"items": auth_store.list_screenings(user["id"])}


@app.delete("/history/screenings/{screening_id}")
def history_screening_delete(screening_id: int, user: dict = Depends(get_current_user)):
    if not auth_store.delete_screening(user["id"], screening_id):
        raise HTTPException(status_code=404, detail="Screening not found.")
    return {"ok": True}


@app.delete("/history/screenings")
def history_screenings_clear(user: dict = Depends(get_current_user)):
    auth_store.clear_screenings(user["id"])
    return {"ok": True}


@app.post("/consultations")
def consultations_create(payload: dict, user: dict = Depends(get_current_user)):
    record = auth_store.add_consultation(user["id"], payload or {})
    return {"item": record}


@app.get("/consultations")
def consultations_list(user: dict = Depends(get_current_user)):
    return {"items": auth_store.list_consultations(user["id"])}


@app.delete("/consultations/{consultation_id}")
def consultation_delete(consultation_id: int, user: dict = Depends(get_current_user)):
    if not auth_store.delete_consultation(user["id"], consultation_id):
        raise HTTPException(status_code=404, detail="Consultation not found.")
    return {"ok": True}


@app.delete("/consultations")
def consultations_clear(user: dict = Depends(get_current_user)):
    auth_store.clear_consultations(user["id"])
    return {"ok": True}


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
async def consultation_socket(websocket: WebSocket, token: str = ""):
    if not token or auth_store.resolve_token(token) is None:
        await websocket.close(code=4401, reason="Sign in to use the live copilot.")
        return
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
