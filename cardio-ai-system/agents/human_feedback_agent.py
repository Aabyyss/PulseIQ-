from __future__ import annotations

from datetime import datetime


def record_feedback_stub(note: str) -> dict:
    return {
        "status": "captured_stub",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "note": note[:200],
    }
