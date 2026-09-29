"""Bridges the per-clinician learned vocabulary into live extraction.

Every extraction call site (websocket line acks, the full pipeline,
screening) passes the overlay from :func:`learned_overlay` so a phrase the
signed-in clinician taught is honoured on the very next line — no restart,
no timers. The overlay is cached per owner and reloaded only when the
store's generation counter changed (any teach/forget bumps it), so the
per-line cost is one small SELECT.
"""

from __future__ import annotations

import threading

from agents.nlp_symptom_agent import extract_symptoms_from_text
from backend import learned_vocabulary

_lock = threading.Lock()
_cache: dict[int, tuple[int, dict]] = {}


def learned_overlay(owner_id: int | None) -> dict | None:
    """Overlay for ``owner_id`` with generation-checked caching."""
    if not owner_id:
        return None
    with _lock:
        cached = _cache.get(owner_id)
        generation = learned_vocabulary.get_generation()
        if cached and cached[0] == generation:
            return cached[1]
    # Load outside the lock; the store read is the slow part.
    overlay = learned_vocabulary.overlay_for(owner_id)
    with _lock:
        _cache[owner_id] = (overlay.get("generation", 0), overlay)
    return overlay


def forget_cached_overlay(owner_id: int) -> None:
    """Drop one owner's cached overlay (used after writes as belt-and-braces)."""
    with _lock:
        _cache.pop(owner_id, None)


def extract_symptoms_for_user(text: str, owner_id: int | None, return_details: bool = False):
    """Extraction with this clinician's learned vocabulary applied."""
    overlay = learned_overlay(owner_id)
    return extract_symptoms_from_text(text, return_details=return_details, learned=overlay)
