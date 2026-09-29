"""Per-clinician learned vocabulary — the persistence half of self-learning.

Clinicians teach PulseIQ their patients' own words: a phrase, the concept it
means, and (optionally) a suppression pattern for phrasings that must never
count as a concept. Everything is scoped by ``owner_id`` at the SQL level —
the same isolation model as auth_store — so what one clinician teaches never
leaks into another account's extractions.

Storage is a separate SQLite database (``backend/data/learned_vocabulary.db``,
override with ``PULSEIQ_LEARNED_DB``) so the security-critical accounts store
stays untouched. Schema migration is additive; existing rows survive upgrades.

Content model
-------------
- Concepts are constrained to the nine clinical concepts the pipeline knows
  (``VALID_CONCEPTS``). Anything else is rejected at the API layer.
- Phrases are lower-cased, whitespace-collapsed, capped at 120 chars, and
  deduplicated per (owner, concept) — teaching the same phrase twice is a
  no-op, not a duplicate.
- Suppression patterns are stored as regex source, validated at write time,
  and recompiled defensively at read time (an invalid pattern is skipped,
  never allowed to crash extraction).
- Learned entries carry an ``origin`` tag: ``feedback`` (taught from the
  concept-chip controls) or ``manual`` (taught from the panel form).

Hot reload
----------
Extraction happens on every spoken line, so the overlay in
``agents.nlp_symptom_agent`` reloads per owner only when the store's
generation counter changed — a single cheap SELECT on each line, no timers.
"""

from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
from typing import Any

# The nine clinical concepts the pipeline maps to model features. Learned
# vocabulary can only extend HOW these are recognised, never invent new
# ones — invented concepts would silently drop out of feature mapping.
VALID_CONCEPTS = frozenset({
    "chest pain", "shortness of breath", "dizziness", "palpitations",
    "fatigue", "nausea", "sweating", "leg swelling", "cough",
})

_MAX_PHRASE = 120
_MAX_PATTERN = 200
_MAX_LEARNED_PER_OWNER = 500

_DB_PATH = os.environ.get(
    "PULSEIQ_LEARNED_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "learned_vocabulary.db"),
)

_lock = threading.Lock()
_initialised = False


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init() -> None:
    global _initialised
    if _initialised:
        return
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS learned_phrases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                concept TEXT NOT NULL,
                phrase TEXT NOT NULL,
                origin TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT NOT NULL,
                UNIQUE(owner_id, concept, phrase)
            );
            CREATE INDEX IF NOT EXISTS idx_learned_owner
                ON learned_phrases(owner_id);
            CREATE TABLE IF NOT EXISTS suppression_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                pattern TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
    _initialised = True


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"


def _bump_generation(conn: sqlite3.Connection) -> None:
    """Invalidate every cached overlay after any vocabulary write."""
    conn.execute(
        "INSERT INTO meta (key, value) VALUES ('generation', ?) "
        "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (str(int(time.time() * 1000)),),
    )


def get_generation() -> int:
    """Monotonic-ish change counter; compared by the hot-reload check."""
    _init()
    with _connect() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = 'generation'").fetchone()
    return int(row["value"]) if row else 0


def _normalise_phrase(phrase: str) -> str:
    return " ".join(str(phrase or "").lower().split())[:_MAX_PHRASE]


# ---------------------------------------------------------------------------
# Write path (taught from the UI)
# ---------------------------------------------------------------------------

def teach_phrase(owner_id: int, concept: str, phrase: str, origin: str = "manual") -> dict[str, Any]:
    """Record that ``phrase`` means ``concept`` for this clinician.

    Returns the stored row (with ``created`` flag) or raises ``ValueError``
    for API-mapped validation failures.
    """
    _init()
    concept_key = str(concept or "").strip().lower()
    if concept_key not in VALID_CONCEPTS:
        raise ValueError(f"Unknown concept. Choose one of: {', '.join(sorted(VALID_CONCEPTS))}.")
    cleaned = _normalise_phrase(phrase)
    if not cleaned:
        raise ValueError("Phrase is required.")
    if origin not in ("feedback", "manual"):
        origin = "manual"
    with _lock, _connect() as conn:
        existing = conn.execute(
            "SELECT id, created_at FROM learned_phrases WHERE owner_id = ? AND concept = ? AND phrase = ?",
            (owner_id, concept_key, cleaned),
        ).fetchone()
        if existing:
            return {
                "id": existing["id"], "concept": concept_key, "phrase": cleaned,
                "origin": origin, "created_at": existing["created_at"], "created": False,
            }
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM learned_phrases WHERE owner_id = ?", (owner_id,)
        ).fetchone()["n"]
        if count >= _MAX_LEARNED_PER_OWNER:
            raise ValueError(
                f"Learned vocabulary is full ({_MAX_LEARNED_PER_OWNER} entries). Remove some first."
            )
        created_at = _now()
        cursor = conn.execute(
            "INSERT INTO learned_phrases (owner_id, concept, phrase, origin, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (owner_id, concept_key, cleaned, origin, created_at),
        )
        _bump_generation(conn)
        return {
            "id": cursor.lastrowid, "concept": concept_key, "phrase": cleaned,
            "origin": origin, "created_at": created_at, "created": True,
        }


def teach_suppression(owner_id: int, pattern: str, note: str = "") -> dict[str, Any]:
    """Record a regex that must never count as a symptom mention.

    The pattern is validated here so extraction never sees an invalid regex.
    """
    _init()
    cleaned = str(pattern or "").strip()[:_MAX_PATTERN]
    if not cleaned:
        raise ValueError("Pattern is required.")
    try:
        re.compile(cleaned, re.IGNORECASE)
    except re.error as exc:
        raise ValueError(f"Not a valid regular expression: {exc}") from exc
    with _lock, _connect() as conn:
        existing = conn.execute(
            "SELECT id FROM suppression_patterns WHERE owner_id = ? AND pattern = ?",
            (owner_id, cleaned),
        ).fetchone()
        if existing:
            raise ValueError("That pattern is already taught.")
        created_at = _now()
        cursor = conn.execute(
            "INSERT INTO suppression_patterns (owner_id, pattern, note, created_at) "
            "VALUES (?, ?, ?, ?)",
            (owner_id, cleaned, str(note or "")[:200], created_at),
        )
        _bump_generation(conn)
        return {"id": cursor.lastrowid, "pattern": cleaned, "note": str(note or "")[:200], "created_at": created_at}


def forget_phrase(owner_id: int, learned_id: int) -> bool:
    _init()
    with _lock, _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM learned_phrases WHERE id = ? AND owner_id = ?", (learned_id, owner_id)
        )
        if cursor.rowcount:
            _bump_generation(conn)
        return cursor.rowcount > 0


def forget_suppression(owner_id: int, suppression_id: int) -> bool:
    _init()
    with _lock, _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM suppression_patterns WHERE id = ? AND owner_id = ?",
            (suppression_id, owner_id),
        )
        if cursor.rowcount:
            _bump_generation(conn)
        return cursor.rowcount > 0


def clear_all(owner_id: int) -> int:
    """Forget everything this clinician taught. Returns the rows removed."""
    _init()
    with _lock, _connect() as conn:
        a = conn.execute("DELETE FROM learned_phrases WHERE owner_id = ?", (owner_id,)).rowcount
        b = conn.execute("DELETE FROM suppression_patterns WHERE owner_id = ?", (owner_id,)).rowcount
        if a or b:
            _bump_generation(conn)
        return a + b


# ---------------------------------------------------------------------------
# Read paths
# ---------------------------------------------------------------------------

def list_vocabulary(owner_id: int) -> dict[str, Any]:
    _init()
    with _connect() as conn:
        phrases = conn.execute(
            "SELECT id, concept, phrase, origin, created_at FROM learned_phrases "
            "WHERE owner_id = ? ORDER BY id DESC",
            (owner_id,),
        ).fetchall()
        suppressions = conn.execute(
            "SELECT id, pattern, note, created_at FROM suppression_patterns "
            "WHERE owner_id = ? ORDER BY id DESC",
            (owner_id,),
        ).fetchall()
    return {
        "phrases": [dict(r) for r in phrases],
        "suppressions": [dict(r) for r in suppressions],
    }


def overlay_for(owner_id: int) -> dict[str, Any]:
    """Load the extraction overlay for one clinician.

    Returns ``{"phrases": {concept: [phrase, ...]}, "suppressions": [compiled
    regex, ...], "generation": int}``. Invalid stored patterns are skipped
    (defensive recompile) rather than allowed to break extraction.
    """
    _init()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT concept, phrase FROM learned_phrases WHERE owner_id = ?", (owner_id,)
        ).fetchall()
        pattern_rows = conn.execute(
            "SELECT pattern FROM suppression_patterns WHERE owner_id = ?", (owner_id,)
        ).fetchall()
        gen_row = conn.execute("SELECT value FROM meta WHERE key = 'generation'").fetchone()
    phrases: dict[str, list[str]] = {}
    for row in rows:
        phrases.setdefault(row["concept"], []).append(row["phrase"])
    suppressions = []
    for row in pattern_rows:
        try:
            suppressions.append(re.compile(row["pattern"], re.IGNORECASE))
        except re.error:
            continue
    return {
        "phrases": phrases,
        "suppressions": suppressions,
        "generation": int(gen_row["value"]) if gen_row else 0,
    }
