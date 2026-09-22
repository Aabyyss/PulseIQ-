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
                probability REAL NOT NULL,
                risk_level TEXT NOT NULL,
                prediction INTEGER NOT NULL,
                symptoms TEXT NOT NULL,
                features TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_screenings_owner
                ON screenings(owner_id, id DESC);
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
    _initialised = True


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
            "INSERT INTO screenings (owner_id, created_at, text, probability, risk_level, "
            "prediction, symptoms, features) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                created_at,
                str(item.get("text", "")),
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
            "SELECT id, created_at, text, probability, risk_level, prediction, symptoms, features "
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
