import asyncio

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend import auth_store, rate_limit
from backend.auth import get_current_user
from backend.orchestrator import run_diagnosis_from_text, run_medication_review
from backend.ai_assistant import (
    analyze_report_image,
    generate_ai_insights,
    generate_final_report_plan,
    get_active_provider,
)
from backend.realtime_service import process_live_transcript_entry
from backend.deidentify import deidentify, deidentify_transcript
from backend.encounter_context import build_medication_context
from backend.fhir_export import build_fhir_bundle
from backend.lab_report import screen_report_text
from backend.medical_entities import build_soap_note, extract_entities
from backend import vocabulary_service
from backend import learned_vocabulary as learning
from agents.nlp_symptom_agent import extract_symptoms_from_text


class NotesUpsert(BaseModel):
    patient_name: str = Field(min_length=1, max_length=120)
    body: str = Field(default="", max_length=20000)


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
    auth_store.record_audit(user["id"], "account.created", payload.email)
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
    auth_store.record_audit(user["id"], "auth.login", _client_ip(request))
    return _session_response(user, token)


@app.post("/auth/logout")
def auth_logout(request: Request, user: dict = Depends(get_current_user)):
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if token:
        auth_store.revoke_token(token)
    auth_store.record_audit(user["id"], "auth.logout")
    return {"ok": True}


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


@app.post("/auth/change-password")
def auth_change_password(payload: PasswordChange, request: Request, user: dict = Depends(get_current_user)):
    try:
        changed = auth_store.change_password(
            user["id"], payload.current_password, payload.new_password
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not changed:
        raise HTTPException(status_code=401, detail="Current password is incorrect.")
    token = auth_store.issue_token(user["id"])
    auth_store.record_audit(user["id"], "auth.password_changed", _client_ip(request))
    return {"token": token, "user": user}


@app.get("/auth/sessions")
def auth_sessions(request: Request, user: dict = Depends(get_current_user)):
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    return {"items": auth_store.list_sessions(user["id"], token or None)}


@app.delete("/auth/sessions/{session_id}")
def auth_session_revoke(session_id: str, user: dict = Depends(get_current_user)):
    ok = auth_store.revoke_session(user["id"], session_id)
    if ok:
        auth_store.record_audit(user["id"], "auth.session_revoked", session_id)
    return {"ok": ok}


@app.post("/auth/sessions/revoke-others")
def auth_sessions_revoke_others(request: Request, user: dict = Depends(get_current_user)):
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    count = auth_store.revoke_other_sessions(user["id"], token or "")
    auth_store.record_audit(user["id"], "auth.others_revoked", str(count))
    return {"revoked": count}


@app.get("/auth/audit")
def auth_audit(user: dict = Depends(get_current_user)):
    return {"items": auth_store.list_audit(user["id"])}


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
    # Privacy: the live analysis sees the original wording, but what gets
    # persisted below is de-identified first (CNIC/phone/email/labeled names).
    stored_text, redactions = deidentify(text)
    if redactions:
        # Audit trail: privacy reviewers can see de-identification happened.
        auth_store.record_audit(
            user["id"], "privacy.redacted",
            ", ".join(f"{k}={v}" for k, v in sorted(redactions.items())),
        )
    # Self-learning: re-extract with the clinician's learned vocabulary and
    # union the findings so taught phrases influence screening exactly as
    # they do live capture.
    learned_symptoms = vocabulary_service.extract_symptoms_for_user(text, user["id"])
    merged = list(result.get("symptoms") or [])
    for symptom in learned_symptoms:
        if symptom not in merged:
            merged.append(symptom)
    if merged != result.get("symptoms"):
        result["symptoms"] = merged
    result["learned_generation"] = learning.get_generation()

    # Persist to the signed-in clinician's history (best-effort; screening
    # itself must not fail if storage hiccups). An optional patient_name lets
    # the clinician file the screening under their own label for that patient.
    try:
        saved = auth_store.add_screening(
            user["id"],
            {**result, "text": stored_text.strip(), "patient_name": (data or {}).get("patient_name", "")},
        )
        result["id"] = saved["id"]
        result["createdAt"] = saved["createdAt"]
        result["patient_name"] = str(saved.get("patient_name") or "")
    except Exception:
        pass

    return result


@app.get("/history/screenings")
def history_screenings(user: dict = Depends(get_current_user)):
    return {"items": auth_store.list_screenings(user["id"])}


@app.post("/symptom-match")
def symptom_match(data: dict, user: dict = Depends(get_current_user)):
    """Inspect what the NLP extractor finds in a narrative, without saving it.

    Debug aid for expanding the symptom dictionary: paste a patient's own
    phrasing (any register) and see the concepts, the exact surface phrases
    that matched, and nothing persisted to history. Runs with the signed-in
    clinician's learned vocabulary applied.
    """
    text = (data or {}).get("text", "")
    if not isinstance(text, str) or not text.strip():
        return {"error": "text is required"}

    symptoms, details = vocabulary_service.extract_symptoms_for_user(
        text, user["id"], return_details=True
    )
    learned = vocabulary_service.learned_overlay(user["id"]) or {}
    learned_count = sum(len(v) for v in (learned.get("phrases") or {}).values()) + len(learned.get("suppressions") or [])
    return {
        "text": text,
        "symptoms": symptoms,
        "matched_phrases": details,
        "count": len(symptoms),
        "learned_generation": learned.get("generation", 0),
        "learned_count": learned_count,
    }


# ---------------------------------------------------------------------------
# Self-learning — per-clinician taught vocabulary (feedback loop)
# ---------------------------------------------------------------------------

class TeachPhraseRequest(BaseModel):
    concept: str = Field(min_length=1, max_length=60)
    phrase: str = Field(min_length=1, max_length=120)
    origin: str = Field(default="manual", pattern="^(feedback|manual)$")


class TeachSuppressionRequest(BaseModel):
    pattern: str = Field(min_length=1, max_length=200)
    note: str = Field(default="", max_length=200)


@app.get("/learning/vocabulary")
def learning_list(user: dict = Depends(get_current_user)):
    """Everything this clinician taught, with the current generation."""
    data = learning.list_vocabulary(user["id"])
    data["generation"] = learning.get_generation()
    data["valid_concepts"] = sorted(learning.VALID_CONCEPTS)
    return data


@app.post("/learning/teach")
def learning_teach(payload: TeachPhraseRequest, user: dict = Depends(get_current_user)):
    """Teach: this phrase means this concept — for my account only.

    The phrase is de-identified first: a taught phrase is derived from what
    a patient said, so it must never carry a name or number into the
    vocabulary store (which is shared across sessions of this account).
    """
    clean_phrase, _ = deidentify(payload.phrase)
    if not clean_phrase.strip():
        raise HTTPException(status_code=422, detail="Phrase is empty after de-identification.")
    try:
        row = learning.teach_phrase(user["id"], payload.concept, clean_phrase, payload.origin)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    vocabulary_service.forget_cached_overlay(user["id"])
    auth_store.record_audit(user["id"], "learning.taught", f"{payload.concept}: {payload.phrase[:80]}")
    return {"item": row, "generation": learning.get_generation()}


@app.post("/learning/suppress")
def learning_suppress(payload: TeachSuppressionRequest, user: dict = Depends(get_current_user)):
    """Teach a suppression: lines matching this regex count as nothing."""
    try:
        row = learning.teach_suppression(user["id"], payload.pattern, payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    vocabulary_service.forget_cached_overlay(user["id"])
    auth_store.record_audit(user["id"], "learning.suppressed", payload.pattern[:80])

    return {"item": row, "generation": learning.get_generation()}


@app.delete("/learning/phrase/{phrase_id}")
def learning_forget_phrase(phrase_id: int, user: dict = Depends(get_current_user)):
    if not learning.forget_phrase(user["id"], phrase_id):
        raise HTTPException(status_code=404, detail="Learned phrase not found.")
    vocabulary_service.forget_cached_overlay(user["id"])
    return {"ok": True, "generation": learning.get_generation()}


@app.delete("/learning/suppression/{suppression_id}")
def learning_forget_suppression(suppression_id: int, user: dict = Depends(get_current_user)):
    if not learning.forget_suppression(user["id"], suppression_id):
        raise HTTPException(status_code=404, detail="Suppression pattern not found.")
    vocabulary_service.forget_cached_overlay(user["id"])
    return {"ok": True, "generation": learning.get_generation()}


@app.delete("/learning/vocabulary")
def learning_clear(user: dict = Depends(get_current_user)):
    removed = learning.clear_all(user["id"])
    vocabulary_service.forget_cached_overlay(user["id"])
    auth_store.record_audit(user["id"], "learning.cleared", str(removed))
    return {"ok": True, "removed": removed, "generation": learning.get_generation()}


# ---------------------------------------------------------------------------
# Clinician notes — private, per (clinician, patient) across all accounts
# ---------------------------------------------------------------------------


@app.get("/notes")
def notes_list(user: dict = Depends(get_current_user)):
    return {"items": auth_store.list_notes(user["id"])}


@app.post("/notes")
def notes_create(data: NotesUpsert, user: dict = Depends(get_current_user)):
    try:
        return auth_store.upsert_note(user["id"], data.patient_name, data.body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Patient timeline — owner-scoped aggregation for one patient label
# ---------------------------------------------------------------------------


@app.get("/patients")
def patients_list(user: dict = Depends(get_current_user)):
    return {"items": auth_store.list_patients(user["id"])}


@app.get("/patients/timeline")
def patient_timeline(patient: str, user: dict = Depends(get_current_user)):
    try:
        timeline = auth_store.patient_timeline(user["id"], patient)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if timeline is None:
        raise HTTPException(status_code=404, detail="Patient not found.")
    return timeline


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
    """Save a visit. Transcript lines are de-identified before storage.

    Patient name / age entered deliberately by the clinician are their own
    filing label and stay as-is; the free-text transcript is what can leak
    identifiers spoken in the room.
    """
    data = dict(payload or {})
    redacted = False
    if isinstance(data.get("lines"), list):
        data["lines"] = deidentify_transcript(data["lines"])
        redacted = redacted or any(
            "[REDACTED" in str(ln.get("text", ""))
            for ln in data["lines"] if isinstance(ln, dict)
        )
    if isinstance(data.get("report_text"), str):
        data["report_text"], counts = deidentify(data["report_text"])
        redacted = redacted or bool(counts)
    if redacted:
        auth_store.record_audit(user["id"], "privacy.redacted", "consultation save")
    record = auth_store.add_consultation(user["id"], data)
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


@app.post("/soap-note")
def soap_note(data: dict, user: dict = Depends(get_current_user)):
    """Structured SOAP note derived strictly from the encounter content.

    Subjective/objective come from what was captured (transcript entities,
    symptom concepts, report context); assessment carries the screening
    band with an explicit not-a-diagnosis qualifier. Nothing is generated
    by an LLM, so it cannot invent findings.
    """
    payload = data or {}
    transcript = payload.get("transcript", "")
    if isinstance(transcript, list):  # list of {speaker,text} lines
        transcript = " ".join(
            str(ln.get("text", "")) for ln in transcript if isinstance(ln, dict)
        )
    if not isinstance(transcript, str):
        transcript = str(transcript)
    symptoms = payload.get("symptoms") or []
    if not isinstance(symptoms, list):
        symptoms = []
    note = build_soap_note(
        transcript=transcript,
        symptoms=[str(s) for s in symptoms],
        report_text=str(payload.get("report_text", "") or ""),
        risk_level=str(payload.get("risk_level", "Low") or "Low"),
    )
    return {"note": note}


@app.post("/extract-entities")
def extract_entities_endpoint(data: dict, user: dict = Depends(get_current_user)):
    """Medications, durations and risk factors in a transcript (no storage)."""
    text = (data or {}).get("text", "")
    if not isinstance(text, str) or not text.strip():
        return {"error": "text is required"}
    return {"entities": extract_entities(text)}


@app.post("/screen-report")
def screen_report(data: dict, user: dict = Depends(get_current_user)):
    """Reference-range screening of report text (labs, ECG statements).

    Flags abnormal and critical values first, each with the exact matched
    text, the reference band it was judged against, and a plain-language
    explanation. Nothing is stored — this is a pure read of the text you
    send. The clinician stays the decision-maker: the output is findings,
    not diagnoses.
    """
    text = (data or {}).get("text", "")
    if not isinstance(text, str) or not text.strip():
        return {"error": "text is required"}
    return screen_report_text(text)


@app.post("/medication-review")
def medication_review(data: dict, user: dict = Depends(get_current_user)):
    """Medication options and safety review for one encounter.

    Everything is derived from what the caller supplies: the narrative and
    report text give concepts, mentioned medications and laboratory values;
    the patient form gives conditions/history, allergies, current medications
    and age. The union rules live in ``backend.encounter_context``, shared with
    the live copilot loop, so the page and a consultation judge the same
    patient identically. Blocks are allergy-, condition- and lab-driven;
    interactions are checked against the documented list. Facts that were not
    supplied are reported back instead of assumed, and nothing is stored.
    """
    payload = data or {}
    text = payload.get("text", "")
    report_text = payload.get("report_text", "")
    if not isinstance(text, str):
        text = ""
    if not isinstance(report_text, str):
        report_text = ""

    context = build_medication_context(text, report_text, payload)

    if not context["narrative"] and not any(
        payload.get(key) for key in ("conditions", "allergies", "current_medications")
    ):
        return {"error": "text, report_text or patient context is required"}

    result = run_medication_review(
        text=text,
        report_text=report_text,
        patient={
            "age": context["age"],
            "sex": context["sex"],
            "conditions": context["conditions"],
            "allergies": context["allergies"],
            "current_medications": context["current_medications"],
            "labs": context["labs"],
            "pregnancy": context["pregnancy"],
        },
    )
    result["extracted"] = {
        "entities": context["entities"],
        "allergies_from_text": context["allergies_from_text"],
        "labs_used": context["labs"],
    }
    return result


@app.post("/fhir-export")
def fhir_export(data: dict, user: dict = Depends(get_current_user)):
    """One encounter's structured findings as a FHIR R4 Bundle (ADR-019).

    Takes the same visit fields the workspace already holds (patient details,
    narrative, report text, risk band, optional final report) and returns an
    EHR-shaped ``Bundle`` of Patient / Practitioner / Encounter / Condition /
    Observation / AllergyIntolerance / MedicationStatement / DetectedIssue /
    DocumentReference resources. Deterministic and offline — no LLM, and
    nothing is stored; the response reports what could not be represented
    (``missing_information``) and what was derived (``caveats``) instead of
    inventing values.
    """
    payload = data or {}
    has_content = any(
        payload.get(key) for key in (
            "text", "report_text", "patient_name", "patient_age", "conditions",
            "allergies", "current_medications", "symptom_notes", "symptoms", "report",
        )
    )
    if not has_content:
        return {"error": "text, report_text or patient context is required"}
    return build_fhir_bundle(payload)


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
            # The visit details the clinician recorded (age, sex, conditions,
            # allergies, current medications) plus everything said before this
            # line: the medication safety screen is rebuilt from all of it, so
            # it cannot drift from what is on screen or survive a transcript
            # clear the client performed.
            patient = message.get("patient") if isinstance(message.get("patient"), dict) else None
            transcript = message.get("transcript") if isinstance(message.get("transcript"), str) else ""
            if not isinstance(text, str) or not text.strip():
                await websocket.send_json({"error": "text is required"})
                continue
            if not isinstance(report_text, str):
                report_text = ""
            if not isinstance(language_code, str) or not language_code.strip():
                language_code = "en-US"
            # Instant ack: echo the line with its regex-extracted symptoms so
            # the UI shows concepts, risk hints and the body map immediately.
            # The full copilot plan needs the local LLM (tens of seconds on
            # CPU), so it follows as a separate message rather than blocking.
            user = auth_store.resolve_token(token)
            owner_id = user["id"] if user else None
            try:
                ack_symptoms, ack_details = vocabulary_service.extract_symptoms_for_user(
                    text, owner_id, return_details=True
                )
                learned = vocabulary_service.learned_overlay(owner_id) or {}
                learned_count = sum(len(v) for v in (learned.get("phrases") or {}).values()) + len(learned.get("suppressions") or [])
                await websocket.send_json({
                    "kind": "line_ack",
                    "speaker": "doctor" if speaker == "doctor" else "patient",
                    "transcript": text,
                    "original_transcript": text,
                    "symptoms": ack_symptoms,
                    "matched_phrases": ack_details,
                    "learned_generation": learned.get("generation", 0),
                    "learned_count": learned_count,
                    "learned_hit": any(
                        str(matched).endswith("(learned)") for matched in ack_details.values()
                    ) or any(p.search(text.lower()) for p in learned.get("suppressions") or []),
                })
            except Exception:
                pass  # client gone; the to_thread result would also fail to send
            # Process off the event loop: the copilot plan can call the
            # local LLM for tens of seconds on CPU, and blocking here would
            # freeze every other request and websocket on the server.
            processed = await asyncio.to_thread(
                process_live_transcript_entry,
                text=text,
                speaker=speaker,
                report_text=report_text,
                language_code=language_code,
                owner_id=owner_id,
                patient=patient,
                transcript=transcript,
            )
            processed["kind"] = "analysis"
            await websocket.send_json(processed)
    except WebSocketDisconnect:
        return
