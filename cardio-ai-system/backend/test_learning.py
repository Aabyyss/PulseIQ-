"""Self-learning loop tests: teach → apply → forget, per-clinician isolation.

Covers the learned-vocabulary store, the extraction overlay (including
negation interaction), and the REST endpoints. Runs the API in-process via
httpx ASGI transport against throwaway databases.

Usage: .venv/Scripts/python.exe backend/test_learning.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Isolated throwaway databases BEFORE importing the app or stores.
_tmpdir = tempfile.mkdtemp(prefix="pulseiq-learning-test-")
os.environ["PULSEIQ_DB"] = os.path.join(_tmpdir, "auth.db")
os.environ["PULSEIQ_LEARNED_DB"] = os.path.join(_tmpdir, "learned.db")

import httpx  # noqa: E402

from agents.nlp_symptom_agent import extract_symptoms_from_text  # noqa: E402
from backend import api_server  # noqa: E402
from backend import learned_vocabulary as lv  # noqa: E402
from backend import vocabulary_service  # noqa: E402

PASS = []
FAIL = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASS.append(name)
        print(f"[PASS] {name}")
    else:
        FAIL.append(name)
        print(f"[FAIL] {name} {detail}")


async def main() -> None:
    transport = httpx.ASGITransport(app=api_server.app)
    client = httpx.AsyncClient(transport=transport, base_url="http://testserver")

    # ------------------------------------------------------------------
    # Store-level behaviour (owner ids 901/902 never collide with the
    # API-created users below, which start at 1 in the fresh auth DB)
    # ------------------------------------------------------------------
    lv.teach_phrase(901, "chest pain", "ghabrahat wala dabao", origin="feedback")
    lv.teach_phrase(901, "fatigue", "jaise battery khatam", origin="manual")

    t1 = "patient says ghabrahat wala dabao since morning"
    symptoms, details = extract_symptoms_from_text(t1, return_details=True, learned=lv.overlay_for(901))
    check("learned phrase fires", symptoms == ["chest pain"], str(symptoms))
    check("learned match is labelled", details.get("chest pain", "").endswith("(learned)"), str(details))

    check(
        "negation still applies to learned phrases",
        extract_symptoms_from_text("no ghabrahat wala dabao", learned=lv.overlay_for(901)) == [],
    )
    check(
        "post-phrase negation applies too",
        extract_symptoms_from_text("ghabrahat wala dabao nahi hai", learned=lv.overlay_for(901)) == [],
    )

    # Per-clinician isolation: overlay for another owner is empty.
    check("isolation: other clinician unaffected", extract_symptoms_from_text(t1, learned=lv.overlay_for(902)) == [])

    # Built-in matching untouched without an overlay (order is a set —
    # the extractor dedupes via set(), so compare membership).
    check(
        "built-in dictionary unchanged without overlay",
        set(extract_symptoms_from_text("chest pain and sweating")) == {"chest pain", "sweating"},
    )

    # Suppression: matching lines count as nothing.
    lv.teach_suppression(901, r"hospital discharge", note="admin chatter")
    check(
        "suppression blanks a matching line",
        extract_symptoms_from_text("chest pain since hospital discharge", learned=lv.overlay_for(901)) == [],
    )

    # Known concepts only.
    try:
        lv.teach_phrase(901, "migraine", "sar dukh")
        check("unknown concept rejected", False, "ValueError not raised")
    except ValueError:
        check("unknown concept rejected", True)

    try:
        lv.teach_suppression(901, "([unclosed")
        check("invalid regex rejected", False, "ValueError not raised")
    except ValueError:
        check("invalid regex rejected", True)

    # Teach → forget round-trip.
    vocab = lv.list_vocabulary(901)
    target = next(p for p in vocab["phrases"] if p["phrase"] == "ghabrahat wala dabao")
    check("forget works", lv.forget_phrase(901, target["id"]))
    check(
        "forgotten phrase stops firing",
        extract_symptoms_from_text(t1, learned=lv.overlay_for(901)) == [],
    )

    # ------------------------------------------------------------------
    # REST endpoints with two clinicians
    # ------------------------------------------------------------------
    r = await client.post("/auth/register", json={"email": "a@x.zz", "password": "learning1", "name": "Dr A"})
    a_token = r.json()["token"]
    r = await client.post("/auth/register", json={"email": "b@x.zz", "password": "learning2", "name": "Dr B"})
    b_token = r.json()["token"]
    a_headers = {"Authorization": f"Bearer {a_token}"}
    b_headers = {"Authorization": f"Bearer {b_token}"}

    # NOTE: "sir halka ho raha" is deliberately NOT in the built-in
    # dictionary, so a match can only come from the learned overlay.
    r = await client.post(
        "/learning/teach", headers=a_headers, json={"concept": "dizziness", "phrase": "sir halka ho raha", "origin": "feedback"}
    )
    check("teach endpoint works", r.status_code == 200 and r.json()["item"]["created"], r.text)

    r = await client.get("/learning/vocabulary", headers=a_headers)
    body = r.json()
    check("list endpoint scoped to teacher", len(body["phrases"]) == 1 and body["phrases"][0]["concept"] == "dizziness", r.text)
    check("valid concepts exposed", "chest pain" in body["valid_concepts"], r.text)

    r = await client.get("/learning/vocabulary", headers=b_headers)
    check("other clinician sees nothing", r.json()["phrases"] == [], r.text)

    r = await client.post(
        "/learning/teach", headers=a_headers, json={"concept": "migraine", "phrase": "x"}
    )
    check("unknown concept via API -> 422", r.status_code == 422, r.text)

    r = await client.post("/learning/teach", json={"concept": "dizziness", "phrase": "x"})
    check("teach requires auth", r.status_code in (401, 403), r.text)

    # Extraction honours the taught phrase through the user-scoped path.
    r = await client.post("/symptom-match", headers=a_headers, json={"text": "sir halka ho raha hai"})
    check(
        "symptom-match applies learned vocab",
        r.json()["symptoms"] == ["dizziness"] and r.json()["matched_phrases"].get("dizziness", "").endswith("(learned)"),
        r.text,
    )
    r = await client.post("/symptom-match", headers=b_headers, json={"text": "sir halka ho raha hai"})
    check("symptom-match isolated per clinician", r.json()["symptoms"] == [], r.text)

    # Screening: taught phrase influences /diagnose for the teaching clinician.
    r = await client.post("/diagnose", headers=a_headers, json={"text": "sir halka ho raha hai"})
    check("diagnose applies learned vocab", "dizziness" in r.json().get("symptoms", []), r.text)

    # Forget via API → stops applying.
    item_id = next(p["id"] for p in body["phrases"] if p["phrase"] == "sir halka ho raha")
    r = await client.delete(f"/learning/phrase/{item_id}", headers=a_headers)
    check("forget endpoint works", r.status_code == 200, r.text)
    r = await client.post("/symptom-match", headers=a_headers, json={"text": "sir halka ho raha hai"})
    check("forgotten phrase no longer applied", r.json()["symptoms"] == [], r.text)

    # Cross-account delete is impossible.
    r2 = await client.post(
        "/learning/teach", headers=a_headers, json={"concept": "cough", "phrase": "khaansi aa rahi", "origin": "manual"}
    )
    cough_id = r2.json()["item"]["id"]
    r = await client.delete(f"/learning/phrase/{cough_id}", headers=b_headers)
    check("cross-account forget rejected", r.status_code == 404, r.text)
    r = await client.get("/learning/vocabulary", headers=a_headers)
    check("phrase survives other user's delete", any(p["id"] == cough_id for p in r.json()["phrases"]), r.text)

    # Clear-all.
    r = await client.delete("/learning/vocabulary", headers=a_headers)
    check("clear endpoint works", r.status_code == 200 and r.json()["removed"] >= 1, r.text)
    r = await client.get("/learning/vocabulary", headers=a_headers)
    check("clear leaves nothing", r.json()["phrases"] == [] and r.json()["suppressions"] == [], r.text)

    await client.aclose()

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
