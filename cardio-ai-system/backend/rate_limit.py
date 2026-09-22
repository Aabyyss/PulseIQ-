"""In-process brute-force protection for the login endpoint.

Fixed-window counters keyed by (client IP, normalised email). Locks an
identity out for LOCKOUT_SECONDS after MAX_ATTEMPTS consecutive failures.
State is memory-only: it resets on server restart, which is acceptable for a
device-local deployment (the attacker is already on the machine) — the goal
is to make credential stuffing slow and noisy, not to survive reboots.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Dict, Tuple

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60  # 15 minutes
_WINDOW_SECONDS = 15 * 60  # failure window the attempts accumulate in

_lock = threading.Lock()
# key -> (fail_count, window_start, locked_until)
_attempts: Dict[Tuple[str, str], Tuple[int, float, float]] = defaultdict(lambda: (0, 0.0, 0.0))


def _normalise_key(ip: str, email: str) -> Tuple[str, str]:
    return (ip.strip() or "unknown", email.strip().lower())


def is_locked(ip: str, email: str) -> int:
    """Return seconds remaining on the lockout, or 0 when allowed."""
    key = _normalise_key(ip, email)
    now = time.time()
    with _lock:
        count, window_start, locked_until = _attempts.get(key, (0, 0.0, 0.0))
        if locked_until > now:
            return int(locked_until - now) + 1
        # Expired window/lock: clear so counting starts fresh.
        if count and now - window_start > _WINDOW_SECONDS:
            _attempts.pop(key, None)
        return 0


def record_failure(ip: str, email: str) -> None:
    """Count a failed attempt; arm the lockout at the threshold."""
    key = _normalise_key(ip, email)
    now = time.time()
    with _lock:
        count, window_start, locked_until = _attempts.get(key, (0, 0.0, 0.0))
        if locked_until > now:
            return  # already locked; nothing to accumulate
        if not count or now - window_start > _WINDOW_SECONDS:
            count, window_start = 0, now
        count += 1
        if count >= MAX_ATTEMPTS:
            _attempts[key] = (count, window_start, now + LOCKOUT_SECONDS)
        else:
            _attempts[key] = (count, window_start, 0.0)


def record_success(ip: str, email: str) -> None:
    """Clear the counter on a successful sign-in."""
    _attempts.pop(_normalise_key(ip, email), None)
