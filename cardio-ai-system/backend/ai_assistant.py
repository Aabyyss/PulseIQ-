import json
import os
import re
from urllib import error, request


# ---------------------------------------------------------------------------
# AI provider strategy (all options are FREE, no key required):
#   1. local   – built-in rule-based clinical engine. Always available,
#                works fully offline. This is the default.
#   2. ollama  – free local LLM (https://ollama.com). Auto-detected when
#                running; upgrade quality with one command: `ollama pull llama3.2`
#   3. gemini  – optional free-tier key, used only if explicitly provided.
# ---------------------------------------------------------------------------

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_MODEL_CANDIDATES = [
    os.getenv("GEMINI_MODEL", "").strip(),
    "gemini-2.0-flash",
    "gemini-1.5-flash-latest",
    "gemini-1.5-flash",
]

_provider_cache: str | None = None
_ollama_checked = False
_ollama_ok = False


def get_active_provider() -> str:
    """Return the active AI provider: 'ollama', 'gemini', or 'local'."""
    global _provider_cache
    if _provider_cache is None:
        if _ollama_available():
            _provider_cache = "ollama"
        elif os.getenv("GEMINI_API_KEY", "").strip():
            _provider_cache = "gemini"
        else:
            _provider_cache = "local"
    return _provider_cache


def reset_provider_cache() -> None:
    """Re-probe providers on next call (used after settings changes)."""
    global _provider_cache, _ollama_checked, _ollama_ok
    _provider_cache = None
    _ollama_checked = False
    _ollama_ok = False


def _ollama_available() -> bool:
    global _ollama_checked, _ollama_ok
    if not _ollama_checked:
        _ollama_checked = True
        try:
            req = request.Request(f"{OLLAMA_BASE_URL}/api/tags", method="GET")
            with request.urlopen(req, timeout=2) as response:
                _ollama_ok = response.status == 200
        except Exception:
            _ollama_ok = False
    return _ollama_ok


# ---------------------------------------------------------------------------
# Generic LLM plumbing
# ---------------------------------------------------------------------------

def _call_ollama(prompt: str, timeout: int, json_mode: bool = False) -> str:
    payload: dict = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
    if json_mode:
        payload["format"] = "json"
    req = request.Request(
        url=f"{OLLAMA_BASE_URL}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body.get("response", "").strip()


def _call_gemini(api_key: str, payload: dict, timeout: int) -> dict:
    errors: list[str] = []
    for model in [m for m in GEMINI_MODEL_CANDIDATES if m]:
        req = request.Request(
            url=f"{GEMINI_API_BASE}/{model}:generateContent?key={api_key}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            errors.append(f"{model}: {exc.read().decode('utf-8', errors='ignore')}")
            continue
        except error.URLError as exc:
            raise RuntimeError("LLM network error.") from exc
    raise RuntimeError(f"LLM error: no compatible model found. Tried: {' | '.join(errors)}")


def _gemini_text(payload: dict, timeout: int) -> str:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")
    body = _call_gemini(api_key=api_key, payload=payload, timeout=timeout)
    try:
        return body["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Unexpected LLM API response format.") from exc


def _safe_parse_json(raw_text: str) -> dict:
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", raw_text)
    if not match:
        raise json.JSONDecodeError("No JSON object found", raw_text, 0)
    return json.loads(match.group(0))


def _llm(prompt: str, timeout: int = 30, json_mode: bool = False) -> str:
    """Call the best available LLM; raise RuntimeError when none can answer."""
    provider = get_active_provider()
    if provider == "ollama":
        try:
            return _call_ollama(prompt, timeout=timeout, json_mode=json_mode)
        except Exception:
            pass  # fall through to gemini/local
    if provider == "gemini" or os.getenv("GEMINI_API_KEY", "").strip():
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        return _gemini_text(payload, timeout=timeout)
    raise RuntimeError("No LLM provider available.")


# ---------------------------------------------------------------------------
# Local rule-based clinical engine (zero configuration, offline capable)
# ---------------------------------------------------------------------------

_EMERGENCY_SIGNS = [
    "Pain or pressure in the chest lasting more than a few minutes",
    "Pain spreading to the jaw, neck, shoulder, or left arm",
    "Severe shortness of breath or difficulty breathing",
    "Fainting, near-fainting, or sudden severe dizziness",
    "Cold sweat, nausea, or pale skin with chest discomfort",
    "Irregular or racing heartbeat with lightheadedness",
]


def _local_insights(text: str, diagnosis: dict) -> str:
    risk = diagnosis.get("risk_level", "Low")
    probability = float(diagnosis.get("probability", 0.0))
    symptoms: list[str] = diagnosis.get("symptoms", []) or []
    symptom_txt = ", ".join(symptoms) if symptoms else "no classic cardiac symptoms"

    summary_lines = [
        f"Screening found a {probability * 100:.0f}% statistical risk pattern ({risk} risk).",
        f"Detected signals: {symptom_txt}.",
        "This is a screening estimate from symptom text only - it is not a diagnosis.",
    ]

    if risk == "High":
        next_steps = [
            "Arrange a medical evaluation within 24 hours.",
            "Ask your clinician about an ECG and basic blood tests.",
            "Avoid intense exercise until you have been assessed.",
            "Keep a note of when symptoms start, how long they last, and what triggers them.",
        ]
    elif risk == "Medium":
        next_steps = [
            "Book a routine or same-week check-up with a clinician.",
            "Monitor blood pressure and resting heart rate if possible.",
            "Reduce caffeine, smoking, and heavy exertion until reviewed.",
            "Record symptom episodes to share at your appointment.",
        ]
    else:
        next_steps = [
            "No urgent action indicated by this screening.",
            "Stay active, hydrate well, and maintain regular check-ups.",
            "Re-run the screening if symptoms change or worsen.",
        ]

    emergency = [
        "Call your local emergency number immediately if any of these occur:",
        *_EMERGENCY_SIGNS[:4],
    ]

    sections = [
        "Summary\n" + "\n".join(f"- {line}" for line in summary_lines),
        "What to do next\n" + "\n".join(f"- {step}" for step in next_steps),
        "Emergency signs\n" + "\n".join(f"- {line}" for line in emergency),
        "This is not medical advice. Always consult a qualified clinician.",
    ]
    return "\n\n".join(sections)


def _local_copilot_plan(text: str, report_text: str, diagnosis: dict, symptoms: list[str]) -> dict:
    risk = diagnosis.get("risk_level", "Low")
    lowered = (text or "").lower()
    report = (report_text or "").lower()

    questions = [
        "When did the symptoms start, and how long does each episode last?",
        "Does anything trigger or relieve the discomfort (exertion, rest, position)?",
        "Any associated sweating, nausea, or breathlessness?",
        "Any history of high blood pressure, diabetes, or smoking?",
        "Any family history of heart disease or sudden cardiac events?",
    ]

    tests = ["Vital signs and pulse oximetry", "12-lead ECG"]
    if "shortness of breath" in symptoms or "breathless" in lowered:
        tests.append("Chest X-ray and BNP")
    if risk != "Low" or "chest" in lowered:
        tests.append("Serial troponin")
    if "palpitations" in symptoms:
        tests.append("Rhythm strip / Holter monitor")
    if any(k in report for k in ("st elevation", "troponin", "echo")):
        tests.append("Echocardiogram")

    urgency = "high" if risk == "High" else ("moderate" if risk == "Medium" else "low")
    next_steps = [
        "Correlate symptoms with ECG and biomarker findings.",
        "Escalate immediately if red-flag symptoms appear.",
        "Document symptom timeline and triggers in the chart.",
    ] if urgency != "low" else [
        "Continue structured history and clinical exam.",
        "Reassess if symptoms progress or new red flags emerge.",
        "Consider outpatient workup per institutional protocol.",
    ]

    impression = []
    if "chest pain" in symptoms or "chest" in lowered:
        impression.append("Chest pain pattern - rule out acute coronary syndrome with ECG/troponin.")
    if "shortness of breath" in symptoms:
        impression.append("Dyspnea - evaluate cardiac vs pulmonary etiology.")
    if "palpitations" in symptoms:
        impression.append("Palpitations - consider arrhythmia; obtain rhythm documentation.")
    if not impression:
        impression.append("Symptom pattern requires clinical correlation with exam and testing.")

    return {
        "doctor_questions": questions[:5],
        "recommended_tests": tests[:5],
        "next_steps": next_steps[:4],
        "diagnostic_impression": impression[:4],
        "urgency": urgency,
        "safety_note": "Decision support only. Confirm with clinical exam and institutional protocol.",
    }


def _local_final_report(payload: dict) -> dict:
    name = payload.get("patient_name", "Patient")
    risk = payload.get("risk_level", "Low")
    complaint = payload.get("chief_complaint", "") or "cardiovascular screening consultation"
    notes: list[str] = payload.get("symptom_notes", []) or []
    tests: list[str] = payload.get("recommended_tests", []) or []
    notes_txt = ", ".join(notes[:6]) if notes else "no specific symptoms captured"

    summary = (
        f"{name} presented for evaluation of {complaint}. Screening risk category: {risk}. "
        f"Documented findings: {notes_txt}."
    )

    red_flags = [
        "Ongoing chest pressure despite rest",
        "Syncope or near-syncope",
        "New severe breathlessness at rest",
        "Hemodynamic instability",
    ]

    return {
        "title": "Consultation Report",
        "summary": summary,
        "probable_diagnosis": [
            "Risk-stratified symptom pattern pending clinical confirmation",
            "Cardiac vs non-cardiac chest pain to be differentiated",
        ],
        "doctor_advice": [
            f"Correlate screening risk ({risk}) with examination and ECG findings.",
            "Obtain the recommended tests before finalizing assessment.",
            "Advise the patient on symptom monitoring and escalation criteria.",
        ],
        "medical_treatment_plan": [
            "Treatment pending diagnostic confirmation.",
            "Address modifiable risk factors (BP, lipids, glucose, smoking).",
            "Initiate protocol-guided therapy once assessment is complete.",
        ],
        "follow_up_plan": [
            "Review test results within 1-2 weeks." if risk != "Low" else "Routine follow-up in 4-6 weeks or as clinically indicated.",
            "Immediate return precautions explained for red-flag symptoms.",
        ],
        "red_flags": red_flags,
        "_recommended_tests": tests[:5],
    }


def _local_image_analysis() -> dict:
    return {
        "summary": "Local analysis could not read the image without an LLM vision model. "
        "Install Ollama with a vision model (e.g. `ollama pull llama3.2-vision`) or add an "
        "optional Gemini key to enable image reading. Text-based features remain fully available.",
        "key_findings": [],
        "possible_diagnosis": [],
        "recommended_tests": [],
        "next_steps": ["Enter key findings manually in the report context field."],
        "red_flags": [],
    }


# ---------------------------------------------------------------------------
# Public API (same signatures as before, so callers need no changes)
# ---------------------------------------------------------------------------

def _build_prompt(text: str, diagnosis: dict) -> str:
    return f"""
You are a medical assistant for educational support only.
You must not diagnose disease or replace professional care.

Patient symptom text:
{text}

Model output:
{json.dumps(diagnosis, indent=2)}

Respond in plain text with exactly 3 short sections:
1) "Summary" (what the model found, simple language)
2) "What to do next" (non-emergency practical next steps)
3) "Emergency signs" (when to seek urgent care)

Keep it under 180 words.
Include a short disclaimer that this is not medical advice.
""".strip()


def generate_ai_insights(text: str, diagnosis: dict) -> str:
    """AI insights for patients. Falls back to the local engine when no LLM is available."""
    try:
        return _llm(_build_prompt(text, diagnosis), timeout=30)
    except (RuntimeError, Exception):
        return _local_insights(text=text, diagnosis=diagnosis)


def _build_copilot_prompt(text: str, report_text: str, diagnosis: dict, symptoms: list[str]) -> str:
    return f"""
You are a clinical decision-support copilot for doctors.
You are not a final diagnosis system.

Patient transcript:
{text}

Report summary:
{report_text}

Extracted symptoms:
{json.dumps(symptoms)}

Model output:
{json.dumps(diagnosis, indent=2)}

Return STRICT JSON with this schema:
{{
  "doctor_questions": ["..."],
  "recommended_tests": ["..."],
  "next_steps": ["..."],
  "diagnostic_impression": ["..."],
  "urgency": "low|moderate|high",
  "safety_note": "..."
}}

Rules:
- 3 to 5 items per list.
- Specific and clinically useful.
- Include emergency escalation in next_steps when red flags exist.
- No markdown, no commentary, JSON only.
""".strip()


def generate_ai_copilot_plan(text: str, report_text: str, diagnosis: dict, symptoms: list[str]) -> dict:
    """Doctor copilot plan. Falls back to the local rule engine when no LLM is available."""
    try:
        raw = _llm(_build_copilot_prompt(text, report_text, diagnosis, symptoms), timeout=30, json_mode=True)
        parsed = _safe_parse_json(raw)
        return {
            "doctor_questions": parsed.get("doctor_questions", []),
            "recommended_tests": parsed.get("recommended_tests", []),
            "next_steps": parsed.get("next_steps", []),
            "diagnostic_impression": parsed.get("diagnostic_impression", []),
            "urgency": parsed.get("urgency", "moderate"),
            "safety_note": parsed.get("safety_note", "Educational support only. Clinical confirmation required."),
        }
    except (RuntimeError, json.JSONDecodeError, Exception):
        return _local_copilot_plan(text=text, report_text=report_text, diagnosis=diagnosis, symptoms=symptoms)


def generate_final_report_plan(payload: dict) -> dict:
    """Consultation report. Falls back to the local template engine when no LLM is available."""
    try:
        prompt = f"""
You are generating a concise doctor-facing consultation report.
Use the provided JSON input and produce STRICT JSON only.

Input:
{json.dumps(payload, indent=2)}

Return schema:
{{
  "title": "Consultation Report",
  "summary": "...",
  "probable_diagnosis": ["..."],
  "doctor_advice": ["..."],
  "medical_treatment_plan": ["..."],
  "follow_up_plan": ["..."],
  "red_flags": ["..."]
}}
Rules:
- 2-5 items per list.
- Keep clinical tone and concise language.
- Include provided patient/doctor details in the summary section.
- No markdown and no extra keys.
""".strip()
        raw = _llm(prompt, timeout=30, json_mode=True)
        parsed = _safe_parse_json(raw)
        return {
            "title": parsed.get("title", "Consultation Report"),
            "summary": parsed.get("summary", ""),
            "probable_diagnosis": parsed.get("probable_diagnosis", []),
            "doctor_advice": parsed.get("doctor_advice", []),
            "medical_treatment_plan": parsed.get("medical_treatment_plan", []),
            "follow_up_plan": parsed.get("follow_up_plan", []),
            "red_flags": parsed.get("red_flags", []),
        }
    except (RuntimeError, json.JSONDecodeError, Exception):
        return _local_final_report(payload=payload)


def analyze_report_image(base64_image: str, mime_type: str = "image/png") -> dict:
    """Report image analysis. Requires a vision-capable LLM; degrades gracefully."""
    provider = get_active_provider()
    if provider == "local":
        return _local_image_analysis()

    prompt = """
You are a clinical report-reading assistant.
Analyze the uploaded report image and extract useful doctor-facing insights.
Return STRICT JSON:
{
  "summary": "...",
  "key_findings": ["..."],
  "possible_diagnosis": ["..."],
  "recommended_tests": ["..."],
  "next_steps": ["..."],
  "red_flags": ["..."]
}
No markdown.
""".strip()

    try:
        if provider == "gemini" or os.getenv("GEMINI_API_KEY", "").strip():
            request_payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                            {"inline_data": {"mime_type": mime_type, "data": base64_image}},
                        ]
                    }
                ]
            }
            raw = _gemini_text(request_payload, timeout=45)
        else:  # ollama with a vision model
            prompt_payload = {
                "model": os.getenv("OLLAMA_VISION_MODEL", "llama3.2-vision"),
                "prompt": prompt,
                "images": [base64_image],
                "stream": False,
                "format": "json",
            }
            req = request.Request(
                url=f"{OLLAMA_BASE_URL}/api/generate",
                data=json.dumps(prompt_payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with request.urlopen(req, timeout=60) as response:
                raw = json.loads(response.read().decode("utf-8")).get("response", "")
        parsed = _safe_parse_json(raw)
        return {
            "summary": parsed.get("summary", ""),
            "key_findings": parsed.get("key_findings", []),
            "possible_diagnosis": parsed.get("possible_diagnosis", []),
            "recommended_tests": parsed.get("recommended_tests", []),
            "next_steps": parsed.get("next_steps", []),
            "red_flags": parsed.get("red_flags", []),
        }
    except (RuntimeError, json.JSONDecodeError, Exception):
        return _local_image_analysis()


def translate_to_english(text: str, language_hint: str = "en-US") -> str:
    """Translate transcript to English. Falls back to original text when no LLM exists."""
    if not text.strip() or language_hint.startswith("en"):
        return text

    try:
        prompt = f"""
Translate the following medical conversation text into concise clinical English.
Keep symptom meaning exact, do not add extra content.
Language hint: {language_hint}

Text:
{text}
""".strip()
        translated = _llm(prompt, timeout=20)
        return translated.strip() or text
    except Exception:
        # No LLM available: return original text. Symptom dictionaries already
        # include common Urdu/Hindi/Roman-Urdu phrases so screening still works.
        return text
