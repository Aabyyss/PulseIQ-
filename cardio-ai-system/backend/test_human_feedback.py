"""The human-in-the-loop feedback stub: what it returns and when.

Small, but it rides every live analysis frame, so its timestamp is checked for
the two things that matter: it is aware UTC (not the deprecated naive
``utcnow()``), and it is a value a client can parse as ISO-8601.

Runnable via pytest and directly (``python backend/test_human_feedback.py``).
"""

import os
import sys
from datetime import datetime, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.human_feedback_agent import record_feedback_stub  # noqa: E402


def test_stub_reports_itself_as_a_stub_with_the_note():
    payload = record_feedback_stub("looked right to me")
    assert payload["status"] == "captured_stub"
    assert payload["note"] == "looked right to me"


def test_the_note_is_capped_so_one_caller_cannot_bloat_a_frame():
    assert len(record_feedback_stub("x" * 5_000)["note"]) == 200


def test_the_timestamp_is_parseable_utc():
    payload = record_feedback_stub("note")
    stamp = payload["timestamp"]
    assert stamp.endswith("Z")
    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timezone.utc.utcoffset(None)
    # Within a minute of now, so the clock is the current one and not a naive
    # local reading mislabelled as UTC.
    drift = abs((datetime.now(timezone.utc) - parsed).total_seconds())
    assert drift < 60, drift


if __name__ == "__main__":  # pragma: no cover - manual run convenience
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
