"""SQLite-backed multi-user store: accounts, sessions, screenings, consultations.

Single-file design (no ORM) so the whole persistence layer is auditable and the
dependency footprint stays at stdlib sqlite3. The database lives at
``backend/data/pulseiq.db`` by default (override with PULSEIQ_DB env var).

Security model
--------------
- Passwords: PBKDF2-HMAC-SHA256, 200k iterations, 16-byte random salt.
- Tokens: 32-byte URL-safe secrets; only the SHA-256 hash is stored, so a
  database leak does not leak usable session tokens.
- Isolation: every history read/write is filtered by ``owner_id`` at the SQL
  level — cross-account access is structurally impossible through this store.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import threading
import time
from typing import Any

_DB_PATH = os.environ.get(
    "PULSEIQ_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "pulseiq.db"),
)

# Session lifetime: 30 days, rolling.
TOKEN_TTL_SECONDS = 30 * 24 * 3600

_PBKDF2_ITERATIONS = 200_000
_MAX_HISTORY_ITEMS = 200

_lock = threading.Lock()
_initialised = False

_BACKUP_DIR = os.path.join(os.path.dirname(_DB_PATH), "backups")
_BACKUPS_TO_KEEP = 10


def backup_database() -> str | None:
    """Copy the DB with SQLite's backup API and checkpoint the WAL.

    Called once at server startup. Keeps the last 10 backups; older ones are
    pruned. Corrupt backups never block startup — worst case the function
    returns None and the server continues on the live DB.
    """
    _init()
    try:
        os.makedirs(_BACKUP_DIR, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = os.path.join(_BACKUP_DIR, f"pulseiq-{stamp}.db")
        with _lock:
            source = sqlite3.connect(_DB_PATH)
            destination = sqlite3.connect(target)
            with destination:
                source.backup(destination)
            # Checkpoint the WAL so the main file is self-contained.
            source.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            source.close()
            destination.close()
        backups = sorted(
            (f for f in os.listdir(_BACKUP_DIR) if f.startswith("pulseiq-") and f.endswith(".db")),
        )
        for old in backups[:-_BACKUPS_TO_KEEP]:
            try:
                os.remove(os.path.join(_BACKUP_DIR, old))
            except OSError:
                pass
        return target
    except Exception:
        return None


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init() -> None:
    global _initialised
    if _initialised:
        return
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                name TEXT NOT NULL DEFAULT '',
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tokens (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS screenings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                text TEXT NOT NULL,
                patient_name TEXT NOT NULL DEFAULT '',
                probability REAL NOT NULL,
                risk_level TEXT NOT NULL,
                prediction INTEGER NOT NULL,
                symptoms TEXT NOT NULL,
                features TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_screenings_owner
                ON screenings(owner_id, id DESC);
            CREATE TABLE IF NOT EXISTS patient_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                patient_name TEXT NOT NULL COLLATE NOCASE,
                body TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                UNIQUE (owner_id, patient_name)
            );
            CREATE INDEX IF NOT EXISTS idx_patient_notes_owner
                ON patient_notes(owner_id, patient_name);
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                action TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_audit_user
                ON audit_log(user_id, id DESC);
            CREATE TABLE IF NOT EXISTS consultations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                title TEXT NOT NULL,
                patient_name TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_consultations_owner
                ON consultations(owner_id, id DESC);
            """
        )
    _migrate(conn)
    _initialised = True


def _migrate(conn: sqlite3.Connection) -> None:
    """Lightweight in-place migrations for databases created pre-notes."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(screenings)").fetchall()}
    if "patient_name" not in cols:
        conn.execute("ALTER TABLE screenings ADD COLUMN patient_name TEXT NOT NULL DEFAULT ''")


# ---------------------------------------------------------------------------
# Password + token primitives
# ---------------------------------------------------------------------------

def _hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ITERATIONS
    )
    return digest.hex()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _normalise_email(email: str) -> str:
    return email.strip().lower()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def create_user(email: str, password: str, name: str = "") -> dict[str, Any]:
    """Register a clinician account. Raises ValueError on duplicate email."""
    _init()
    email = _normalise_email(email)
    if "@" not in email or len(email) > 254:
        raise ValueError("Enter a valid email address.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if len(password) > 256:
        raise ValueError("Password is too long.")

    salt = secrets.token_bytes(16).hex()
    password_hash = _hash_password(password, salt)
    now = time.time()

    with _lock, _connect() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO users (email, name, password_hash, salt, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (email, name.strip(), password_hash, salt, now),
            )
        except sqlite3.IntegrityError:
            raise ValueError("An account with this email already exists.") from None
        return {"id": cursor.lastrowid, "email": email, "name": name.strip()}


def verify_user(email: str, password: str) -> dict[str, Any] | None:
    """Return the user row when the credentials match, else None."""
    _init()
    email = _normalise_email(email)
    with _lock, _connect() as conn:
        row = conn.execute(
            "SELECT id, email, name, password_hash, salt FROM users WHERE email = ?", (email,)
        ).fetchone()
    if row is None:
        # Burn comparable time so missing accounts are not distinguishable.
        _hash_password(password, "00" * 16)
        return None
    candidate = _hash_password(password, row["salt"])
    if not hmac.compare_digest(candidate, row["password_hash"]):
        return None
    return {"id": row["id"], "email": row["email"], "name": row["name"]}


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    _init()
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, email, name FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return dict(row) if row else None


def count_users() -> int:
    _init()
    with _connect() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def issue_token(user_id: int) -> str:
    """Create a session token; only its SHA-256 hash is persisted."""
    _init()
    token = secrets.token_urlsafe(32)
    now = time.time()
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT INTO tokens (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (_token_hash(token), user_id, now, now + TOKEN_TTL_SECONDS),
        )
        # Opportunistic cleanup of expired sessions.
        conn.execute("DELETE FROM tokens WHERE expires_at < ?", (now,))
    return token


def resolve_token(token: str) -> dict[str, Any] | None:
    """Map a bearer token to its user, or None when invalid/expired."""
    _init()
    if not token:
        return None
    now = time.time()
    with _connect() as conn:
        row = conn.execute(
            "SELECT u.id, u.email, u.name FROM tokens t "
            "JOIN users u ON u.id = t.user_id "
            "WHERE t.token_hash = ? AND t.expires_at > ?",
            (_token_hash(token), now),
        ).fetchone()
    return dict(row) if row else None


def revoke_token(token: str) -> None:
    _init()
    with _lock, _connect() as conn:
        conn.execute("DELETE FROM tokens WHERE token_hash = ?", (_token_hash(token),))


def list_sessions(user_id: int, current_token: str | None = None) -> list[dict[str, Any]]:
    """The clinician's active sessions, newest first."""
    _init()
    current_hash = _token_hash(current_token) if current_token else None
    now = time.time()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT token_hash, created_at, expires_at FROM tokens "
            "WHERE user_id = ? AND expires_at > ? ORDER BY created_at DESC",
            (user_id, now),
        ).fetchall()
    sessions = []
    for row in rows:
        sessions.append(
            {
                "id": row["token_hash"][:12],
                "created_at": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime(row["created_at"])
                ),
                "expires_at": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime(row["expires_at"])
                ),
                "current": bool(current_hash and row["token_hash"] == current_hash),
            }
        )
    return sessions


def revoke_session(user_id: int, session_id: str) -> bool:
    """Revoke one of the clinician's sessions by its public id prefix."""
    _init()
    with _lock, _connect() as conn:
        rows = conn.execute(
            "SELECT token_hash FROM tokens WHERE user_id = ? AND expires_at > ?",
            (user_id, time.time()),
        ).fetchall()
        for row in rows:
            if row["token_hash"][:12] == session_id:
                conn.execute("DELETE FROM tokens WHERE token_hash = ?", (row["token_hash"],))
                return True
    return False


def revoke_other_sessions(user_id: int, current_token: str) -> int:
    """Sign out every session except the current one. Returns count revoked."""
    _init()
    current_hash = _token_hash(current_token)
    with _lock, _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM tokens WHERE user_id = ? AND token_hash != ?",
            (user_id, current_hash),
        )
        return cursor.rowcount


def change_password(user_id: int, current_password: str, new_password: str) -> bool:
    """Rotate the password after verifying the current one.

    All other sessions are revoked so stolen tokens die with the change.
    """
    _init()
    with _connect() as conn:
        row = conn.execute(
            "SELECT password_hash, salt FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    if row is None or _hash_password(current_password, row["salt"]) != row["password_hash"]:
        return False
    if len(new_password) < 8 or len(new_password) > 256:
        raise ValueError("New password must be 8-256 characters.")
    salt = secrets.token_bytes(16).hex()
    new_hash = _hash_password(new_password, salt)
    with _lock, _connect() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ?, salt = ? WHERE id = ?",
            (new_hash, salt, user_id),
        )
        conn.execute(
            "DELETE FROM tokens WHERE user_id = ? AND token_hash != ?",
            (user_id, "__none__"),  # revoke all; caller re-issues a fresh token
        )
    return True


# ---------------------------------------------------------------------------
# Screening history (owner-scoped)
# ---------------------------------------------------------------------------

def add_screening(user_id: int, item: dict[str, Any]) -> dict[str, Any]:
    _init()
    symptoms = item.get("symptoms") or []
    features = item.get("features") or []
    created_at = item.get("createdAt") or time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"
    with _lock, _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO screenings (owner_id, created_at, text, patient_name, probability, risk_level, "
            "prediction, symptoms, features) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                created_at,
                str(item.get("text", "")),
                str(item.get("patient_name", "") or ""),
                float(item.get("probability", 0.0)),
                str(item.get("risk_level", "Low")),
                int(item.get("prediction", 0)),
                json_dumps(symptoms),
                json_dumps(features),
            ),
        )
        item = {**item, "id": cursor.lastrowid, "createdAt": created_at}
    return item


def list_screenings(user_id: int, limit: int = _MAX_HISTORY_ITEMS) -> list[dict[str, Any]]:
    _init()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, created_at, text, patient_name, probability, risk_level, prediction, symptoms, features "
            "FROM screenings WHERE owner_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    items = []
    for row in rows:
        items.append(
            {
                "id": row["id"],
                "createdAt": row["created_at"],
                "text": row["text"],
                "patient_name": row["patient_name"],
                "probability": row["probability"],
                "risk_level": row["risk_level"],
                "prediction": row["prediction"],
                "symptoms": json_loads(row["symptoms"]),
                "features": json_loads(row["features"]),
            }
        )
    return items


def delete_screening(user_id: int, screening_id: int) -> bool:
    _init()
    with _lock, _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM screenings WHERE id = ? AND owner_id = ?", (screening_id, user_id)
        )
        return cursor.rowcount > 0


def clear_screenings(user_id: int) -> None:
    _init()
    with _lock, _connect() as conn:
        conn.execute("DELETE FROM screenings WHERE owner_id = ?", (user_id,))


# ---------------------------------------------------------------------------
# Clinician notes — private, owner-scoped, one note per patient name
# ---------------------------------------------------------------------------

def record_audit(user_id: int | None, action: str, detail: str = "") -> None:
    """Append an audit entry. Best-effort: never raises to the caller."""
    try:
        _init()
        created_at = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"
        with _lock, _connect() as conn:
            conn.execute(
                "INSERT INTO audit_log (user_id, action, detail, created_at) VALUES (?, ?, ?, ?)",
                (user_id, str(action)[:64], str(detail or "")[:512], created_at),
            )
    except Exception:
        pass


def list_audit(user_id: int, limit: int = 100) -> list[dict[str, Any]]:
    """The clinician's own audit trail, newest first."""
    _init()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT action, detail, created_at FROM audit_log "
            "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [
        {"action": row["action"], "detail": row["detail"], "created_at": row["created_at"]}
        for row in rows
    ]


def _normalise_patient(name: str) -> str:
    cleaned = " ".join(str(name or "").split())
    if not cleaned or len(cleaned) > 120:
        raise ValueError("Patient name must be 1–120 characters.")
    return cleaned


def upsert_note(user_id: int, patient_name: str, body: str) -> dict[str, Any]:
    """Create or replace the signed-in clinician's note for a patient."""
    _init()
    patient = _normalise_patient(patient_name)
    body = str(body or "")[:20000]
    updated_at = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT INTO patient_notes (owner_id, patient_name, body, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT (owner_id, patient_name) "
            "DO UPDATE SET body = excluded.body, updated_at = excluded.updated_at",
            (user_id, patient, body, updated_at),
        )
    return {"patient_name": patient, "body": body, "updated_at": updated_at}


def list_notes(user_id: int) -> list[dict[str, Any]]:
    _init()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT patient_name, body, updated_at FROM patient_notes "
            "WHERE owner_id = ? ORDER BY updated_at DESC",
            (user_id,),
        ).fetchall()
    return [
        {"patient_name": row["patient_name"], "body": row["body"], "updated_at": row["updated_at"]}
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Patient timeline — owner-scoped aggregation across records for one patient
# ---------------------------------------------------------------------------

def list_patients(user_id: int) -> list[dict[str, Any]]:
    """Distinct patient labels the clinician has used, with record counts.

    Sources: screenings, notes and consultations. Names are merged
    case-insensitively; the most recent spelling wins.
    """
    _init()
    merged: dict[str, dict[str, Any]] = {}
    with _connect() as conn:
        for table, count_key, stamp_col, extra in (
            ("screenings", "screenings", "created_at", "AND patient_name != ''"),
            ("patient_notes", "notes", "updated_at", ""),
            ("consultations", "consultations", "created_at", "AND patient_name != ''"),
        ):
            rows = conn.execute(
                f"SELECT patient_name, COUNT(*) AS n, MAX({stamp_col}) AS last "
                f"FROM {table} WHERE owner_id = ? {extra} "
                f"GROUP BY patient_name COLLATE NOCASE",
                (user_id,),
            ).fetchall()
            for row in rows:
                # Merge case and spacing variants under one canonical key.
                canonical = " ".join(row["patient_name"].split())
                key = canonical.casefold()
                entry = merged.setdefault(
                    key,
                    {"patient_name": canonical, "screenings": 0,
                     "notes": 0, "consultations": 0, "last_activity": ""},
                )
                entry[count_key] += row["n"]
                if row["last"] and row["last"] > entry["last_activity"]:
                    entry["last_activity"] = row["last"]
                    entry["patient_name"] = canonical
    items = sorted(merged.values(), key=lambda e: e["last_activity"], reverse=True)
    for entry in items:
        entry["total"] = entry["screenings"] + entry["consultations"] + (1 if entry["notes"] else 0)
    return items


def patient_timeline(user_id: int, patient_name: str) -> dict[str, Any] | None:
    """All records the clinician tagged with this patient name, owner-scoped.

    Case and whitespace variants of the name are merged, matching the
    grouping used by :func:`list_patients`. Returns None when the clinician
    has no record under that name.
    """
    _init()
    canonical_key = " ".join(str(patient_name or "").split()).casefold()
    if not canonical_key:
        raise ValueError("Patient name is required.")

    with _connect() as conn:
        variants: list[str] = []
        for table in ("screenings", "patient_notes", "consultations"):
            for row in conn.execute(
                f"SELECT DISTINCT patient_name FROM {table} WHERE owner_id = ?",
                (user_id,),
            ).fetchall():
                if " ".join(row["patient_name"].split()).casefold() == canonical_key:
                    if row["patient_name"] not in variants:
                        variants.append(row["patient_name"])
        if not variants:
            return None

        placeholders = ",".join("?" for _ in variants)
        params = [user_id, *variants]

        screening_rows = conn.execute(
            f"SELECT id, created_at, text, probability, risk_level, prediction, symptoms, features "
            f"FROM screenings WHERE owner_id = ? AND patient_name IN ({placeholders}) "
            f"ORDER BY id DESC",
            params,
        ).fetchall()
        note_rows = conn.execute(
            f"SELECT patient_name, body, updated_at FROM patient_notes "
            f"WHERE owner_id = ? AND patient_name IN ({placeholders})",
            params,
        ).fetchall()
        consultation_rows = conn.execute(
            f"SELECT id, created_at, title, payload FROM consultations "
            f"WHERE owner_id = ? AND patient_name IN ({placeholders}) ORDER BY id DESC",
            params,
        ).fetchall()
        consultation_display = conn.execute(
            f"SELECT patient_name FROM consultations WHERE owner_id = ? AND patient_name IN ({placeholders}) "
            f"ORDER BY id DESC LIMIT 1",
            params,
        ).fetchone()
        screening_display = conn.execute(
            f"SELECT patient_name FROM screenings WHERE owner_id = ? AND patient_name IN ({placeholders}) "
            f"ORDER BY id DESC LIMIT 1",
            params,
        ).fetchone()

    # Prefer the deliberately-typed note spelling for display, then the most
    # recent consultation, then the most recent screening label.
    if note_rows:
        display = note_rows[0]["patient_name"]
    elif consultation_display:
        display = consultation_display["patient_name"]
    elif screening_display:
        display = screening_display["patient_name"]
    else:
        display = variants[0]

    return {
        "patient_name": " ".join(display.split()),
        "screenings": [
            {
                "id": row["id"],
                "createdAt": row["created_at"],
                "text": row["text"],
                "probability": row["probability"],
                "risk_level": row["risk_level"],
                "prediction": row["prediction"],
                "symptoms": json_loads(row["symptoms"]),
                "features": json_loads(row["features"]),
            }
            for row in screening_rows
        ],
        "note": (
            {"body": note_rows[0]["body"], "updated_at": note_rows[0]["updated_at"]}
            if note_rows else None
        ),
        "consultations": [
            {
                "id": row["id"],
                "createdAt": row["created_at"],
                "title": row["title"],
                "payload": json_loads(row["payload"]),
            }
            for row in consultation_rows
        ],
    }


# ---------------------------------------------------------------------------
# Consultation records (owner-scoped)
# ---------------------------------------------------------------------------

def add_consultation(user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    _init()
    created_at = payload.get("createdAt") or time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"
    title = str(payload.get("title") or "").strip()
    if not title:
        patient = str(payload.get("patient_name") or "").strip()
        title = f"Consultation — {patient}" if patient else "Consultation"
    with _lock, _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO consultations (owner_id, created_at, title, patient_name, payload) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, created_at, title, str(payload.get("patient_name") or ""), json_dumps(payload)),
        )
        return {**payload, "id": cursor.lastrowid, "createdAt": created_at, "title": title}


def list_consultations(user_id: int, limit: int = _MAX_HISTORY_ITEMS) -> list[dict[str, Any]]:
    _init()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, created_at, title, patient_name, payload FROM consultations "
            "WHERE owner_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    items = []
    for row in rows:
        payload = json_loads(row["payload"])
        items.append(
            {
                "id": row["id"],
                "createdAt": row["created_at"],
                "title": row["title"],
                "patient_name": row["patient_name"],
                **payload,
            }
        )
    return items


def delete_consultation(user_id: int, consultation_id: int) -> bool:
    _init()
    with _lock, _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM consultations WHERE id = ? AND owner_id = ?", (consultation_id, user_id)
        )
        return cursor.rowcount > 0


def clear_consultations(user_id: int) -> None:
    _init()
    with _lock, _connect() as conn:
        conn.execute("DELETE FROM consultations WHERE owner_id = ?", (user_id,))


# ---------------------------------------------------------------------------
# JSON helpers (kept tiny; stdlib json)
# ---------------------------------------------------------------------------

import json  # noqa: E402  (placed last to keep the security docstring at top)


def json_dumps(value: Any) -> str:
    return json.dumps(value)


def json_loads(value: str) -> Any:
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return []
