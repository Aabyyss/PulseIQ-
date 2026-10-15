from __future__ import annotations

from datetime import datetime, timezone


def record_feedback_stub(note: str) -> dict:
    """Timestamped feedback capture (the human-in-the-loop stub).

    The timestamp is built from an aware UTC clock: ``datetime.utcnow()`` is
    deprecated and scheduled for removal, and it produced a naive datetime whose
    meaning depended on the reader rather than on the value — Python 3.12+ warns
    on every live frame for it. Still a stub: the payload notes where it came
    from so a caller cannot mistake it for a persisted record.
    """
    return {
        "status": "captured_stub",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "note": note[:200],
    }
