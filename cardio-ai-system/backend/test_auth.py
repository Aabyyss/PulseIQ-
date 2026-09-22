"""Multi-user auth + data-isolation tests.

Runs the API in-process via httpx ASGI transport. Exercises registration,
login, token auth, per-user screening history, and the isolation guarantee:
one account can never read or delete another account's records.

Usage: .venv/Scripts/python.exe backend/test_auth.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Isolated throwaway database for the test run.
_tmpdir = tempfile.mkdtemp(prefix="pulseiq-test-")
os.environ["PULSEIQ_DB"] = os.path.join(_tmpdir, "test.db")

import httpx  # noqa: E402

from backend import api_server  # noqa: E402

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

    # ------------------------------------------------------------------ #
    # Registration + login
    # ------------------------------------------------------------------ #
    r = await client.post(
        "/auth/register",
        json={"email": "dr.house@hospital.org", "password": "vitamin12", "name": "Gregory House"},
    )
    check("register returns token", r.status_code == 200 and bool(r.json().get("token")), r.text)
    house_token = r.json().get("token", "")

    r = await client.post(
        "/auth/register",
        json={"email": "dr.house@hospital.org", "password": "vitamin12"},
    )
    check("duplicate email rejected", r.status_code == 400, r.text)

    r = await client.post("/auth/register", json={"email": "x@y.zz", "password": "short"})
    check("weak password rejected", r.status_code == 422, r.text)

    r = await client.post("/auth/login", json={"email": "dr.house@hospital.org", "password": "wrong-pass"})
    check("wrong password -> 401", r.status_code == 401, r.text)

    r = await client.post("/auth/login", json={"email": "dr.house@hospital.org", "password": "vitamin12"})
    check("login works", r.status_code == 200 and bool(r.json().get("token")), r.text)
    house_token = r.json().get("token", "")
    house_headers = {"Authorization": f"Bearer {house_token}"}

    r = await client.post(
        "/auth/register",
        json={"email": "dr.wilson@hospital.org", "password": "oncology9", "name": "James Wilson"},
    )
    wilson_token = r.json().get("token", "")
    wilson_headers = {"Authorization": f"Bearer {wilson_token}"}

    # ------------------------------------------------------------------ #
    # Endpoint protection
    # ------------------------------------------------------------------ #
    r = await client.post("/diagnose", json={"text": "crushing chest pain radiating to left arm"})
    check("diagnose requires auth", r.status_code == 401, r.text)

    r = await client.get("/history/screenings", headers={"Authorization": "Bearer garbage"})
    check("bad token rejected", r.status_code == 401, r.text)

    r = await client.get("/auth/me", headers=house_headers)
    check("/auth/me returns user", r.status_code == 200 and r.json()["user"]["email"] == "dr.house@hospital.org", r.text)

    # ------------------------------------------------------------------ #
    # Screening history + isolation
    # ------------------------------------------------------------------ #
    r = await client.post("/diagnose", headers=house_headers, json={"text": "crushing chest pain with sweating and left arm pain"})
    check("diagnose works with token", r.status_code == 200 and r.json().get("probability", 0) > 0.5, r.text)
    house_screening_id = r.json().get("id")

    await client.post("/diagnose", headers=house_headers, json={"text": "mild fatigue after work"})
    await client.post("/diagnose", headers=wilson_headers, json={"text": "sharp chest pain when breathing deeply"})

    r = await client.get("/history/screenings", headers=house_headers)
    house_items = r.json().get("items", [])
    check("house sees own screenings", r.status_code == 200 and len(house_items) == 2, str(len(house_items)))

    r = await client.get("/history/screenings", headers=wilson_headers)
    wilson_items = r.json().get("items", [])
    check("wilson sees only own screenings", r.status_code == 200 and len(wilson_items) == 1, str(len(wilson_items)))
    check(
        "wilson cannot see house data",
        all("sweating" not in item["text"] for item in wilson_items),
    )

    # Cross-account deletion must fail with 404.
    r = await client.delete(f"/history/screenings/{house_screening_id}", headers=wilson_headers)
    check("cross-account delete blocked", r.status_code == 404, r.text)

    r = await client.delete(f"/history/screenings/{house_screening_id}", headers=house_headers)
    check("owner delete works", r.status_code == 200, r.text)

    # ------------------------------------------------------------------ #
    # Consultations + isolation
    # ------------------------------------------------------------------ #
    r = await client.post(
        "/consultations",
        headers=house_headers,
        json={"patient_name": "Patient A", "risk_level": "High", "symptom_notes": ["chest pain"]},
    )
    check("consultation saved", r.status_code == 200 and r.json()["item"]["id"] > 0, r.text)
    house_consult_id = r.json()["item"]["id"]

    await client.post("/consultations", headers=wilson_headers, json={"patient_name": "Patient B"})

    r = await client.get("/consultations", headers=house_headers)
    check("house sees 1 consultation", len(r.json().get("items", [])) == 1, r.text)

    r = await client.get("/consultations", headers=wilson_headers)
    check("wilson sees only own consultations", len(r.json().get("items", [])) == 1 and r.json()["items"][0]["patient_name"] == "Patient B", r.text)

    r = await client.delete(f"/consultations/{house_consult_id}", headers=wilson_headers)
    check("cross-account consultation delete blocked", r.status_code == 404, r.text)

    # ------------------------------------------------------------------ #
    # Logout revokes the session
    # ------------------------------------------------------------------ #
    r = await client.post("/auth/logout", headers=wilson_headers)
    check("logout ok", r.status_code == 200, r.text)

    r = await client.get("/history/screenings", headers=wilson_headers)
    check("token revoked after logout", r.status_code == 401, r.text)

    # Public endpoints stay open.
    r = await client.get("/health")
    check("/health stays public", r.status_code == 200, r.text)

    # ------------------------------------------------------------------ #
    # Brute-force lockout (5 fails -> 429 until the window clears)
    # ------------------------------------------------------------------ #
    for _ in range(5):
        r = await client.post(
            "/auth/login", json={"email": "dr.chen@hospital.org", "password": "wrong-wrong"}
        )
    check("5th failure still 401", r.status_code == 401, r.text)
    r = await client.post(
        "/auth/login", json={"email": "dr.chen@hospital.org", "password": "vitamin12"}
    )
    # NOTE: chen's real password differs in this DB; the point is 429, not 200.
    check("lockout triggers 429", r.status_code == 429, r.text)

    # A different account is not locked by chen's failures.
    r = await client.post("/auth/login", json={"email": "nobody@hospital.org", "password": "whatever1"})
    check("other accounts unaffected", r.status_code == 401, r.text)

    await client.aclose()

    print()
    print(f"{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("Failed:", FAIL)
        sys.exit(1)
    print("All auth tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
