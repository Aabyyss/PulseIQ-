"""Login throttling: the lockout it promises, and the memory it must not eat.

The brute-force limiter was the one security control with no test at all, and it
had a growth problem: every failed attempt added an entry keyed by (IP, email)
and nothing ever removed one, so a script walking a list of addresses grew the
map for the life of the process. These cases pin both halves — the lockout still
arms, clears and expires, and the map stays bounded while it does.

Runnable via pytest and directly (``python backend/test_rate_limit.py``).
"""

import os
import sys
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend import rate_limit  # noqa: E402


def _fresh():
    """Snapshot the module's state so a case can leave no trace behind."""
    state = (dict(rate_limit._attempts), rate_limit._writes_since_sweep)
    rate_limit._attempts.clear()
    rate_limit._writes_since_sweep = 0
    return state


def _restore(state):
    attempts, writes = state
    rate_limit._attempts.clear()
    rate_limit._attempts.update(attempts)
    rate_limit._writes_since_sweep = writes


def test_lockout_arms_at_the_threshold_and_a_success_clears_it():
    state = _fresh()
    try:
        for _ in range(rate_limit.MAX_ATTEMPTS - 1):
            rate_limit.record_failure("10.0.0.1", "doc@cardio.local")
        assert rate_limit.is_locked("10.0.0.1", "doc@cardio.local") == 0
        rate_limit.record_failure("10.0.0.1", "doc@cardio.local")
        remaining = rate_limit.is_locked("10.0.0.1", "doc@cardio.local")
        assert remaining > 0
        assert remaining <= rate_limit.LOCKOUT_SECONDS
        # A different identity is untouched by it.
        assert rate_limit.is_locked("10.0.0.1", "other@cardio.local") == 0
        rate_limit.record_success("10.0.0.1", "doc@cardio.local")
        assert rate_limit.is_locked("10.0.0.1", "doc@cardio.local") == 0
    finally:
        _restore(state)


def test_the_lockout_lifts_when_its_window_passes(monkeypatch):
    state = _fresh()
    try:
        clock = {"now": 1_000.0}
        monkeypatch.setattr(rate_limit.time, "time", lambda: clock["now"])
        for _ in range(rate_limit.MAX_ATTEMPTS):
            rate_limit.record_failure("10.0.0.2", "doc@cardio.local")
        assert rate_limit.is_locked("10.0.0.2", "doc@cardio.local") > 0
        clock["now"] += rate_limit.LOCKOUT_SECONDS + 1
        assert rate_limit.is_locked("10.0.0.2", "doc@cardio.local") == 0
    finally:
        _restore(state)


def test_failures_only_count_inside_their_window(monkeypatch):
    state = _fresh()
    try:
        clock = {"now": 5_000.0}
        monkeypatch.setattr(rate_limit.time, "time", lambda: clock["now"])
        for _ in range(rate_limit.MAX_ATTEMPTS - 1):
            rate_limit.record_failure("10.0.0.3", "doc@cardio.local")
        # The window lapses before the next failure: counting starts over.
        clock["now"] += rate_limit._WINDOW_SECONDS + 1
        rate_limit.record_failure("10.0.0.3", "doc@cardio.local")
        assert rate_limit.is_locked("10.0.0.3", "doc@cardio.local") == 0
    finally:
        _restore(state)


def test_the_tracked_identities_stay_bounded():
    state = _fresh()
    try:
        for index in range(rate_limit._MAX_TRACKED * 2):
            rate_limit.record_failure(f"10.1.{index // 250}.{index % 250}", f"user{index}@cardio.local")
        # Bounded, not exact: the cap is enforced by the sweep, so up to one
        # sweep interval of new entries can sit above it (a sweep per insert
        # would make every attempt O(n)).
        assert len(rate_limit._attempts) <= rate_limit._MAX_TRACKED + rate_limit._SWEEP_EVERY
        # Bounding must not disarm the limiter for the identity that matters.
        for _ in range(rate_limit.MAX_ATTEMPTS):
            rate_limit.record_failure("192.168.0.9", "target@cardio.local")
        assert rate_limit.is_locked("192.168.0.9", "target@cardio.local") > 0
    finally:
        _restore(state)


def test_expired_counters_are_swept_without_waiting_for_the_cap(monkeypatch):
    state = _fresh()
    try:
        clock = {"now": 2_000.0}
        monkeypatch.setattr(rate_limit.time, "time", lambda: clock["now"])
        for index in range(50):
            rate_limit.record_failure("10.2.0.1", f"user{index}@cardio.local")
        clock["now"] += rate_limit._WINDOW_SECONDS + 1
        for _ in range(rate_limit._SWEEP_EVERY):
            rate_limit.record_failure("10.2.0.2", "another@cardio.local")
        # Everything from the lapsed window is gone; only the live key remains.
        assert list(rate_limit._attempts) == [("10.2.0.2", "another@cardio.local")]
    finally:
        _restore(state)


if __name__ == "__main__":  # pragma: no cover - manual run convenience
    for _name, _case in sorted(globals().items()):
        if _name.startswith("test_") and callable(_case):
            _case()
            print(f"[PASS] {_name}")
    print("rate limit: ok")
    time.sleep(0)
