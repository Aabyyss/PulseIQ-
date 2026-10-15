"""In-process brute-force protection for the login endpoint.

Fixed-window counters keyed by (client IP, normalised email). Locks an
identity out for LOCKOUT_SECONDS after MAX_ATTEMPTS consecutive failures.
State is memory-only: it resets on server restart, which is acceptable for a
device-local deployment (the attacker is already on the machine) — the goal
is to make credential stuffing slow and noisy, not to survive reboots.

Memory is bounded on purpose. A counter is only useful while it is inside its
window, so expired ones are swept as writes come in, and the map is capped:
past ``_MAX_TRACKED`` identities the oldest counters are dropped, except any
that are currently locked out. Without both, a script that walks a million
addresses would keep a million tuples alive for the whole run — a limiter that
turns a password guess into a memory exhaustion.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Dict, Tuple

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60  # 15 minutes
_WINDOW_SECONDS = 15 * 60  # failure window the attempts accumulate in

# Housekeeping: sweep every N writes, and never track more than this many
# identities at once (locked-out ones are exempt — they are the whole point).
_SWEEP_EVERY = 256
_MAX_TRACKED = 10_000

_lock = threading.Lock()
# key -> (fail_count, window_start, locked_until)
_attempts: Dict[Tuple[str, str], Tuple[int, float, float]] = defaultdict(lambda: (0, 0.0, 0.0))
_writes_since_sweep = 0


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


def _expired(count: int, window_start: float, locked_until: float, now: float) -> bool:
    """True when this counter can neither lock nor count anybody any more."""
    if locked_until > now:
        return False
    return not count or now - window_start > _WINDOW_SECONDS


def _housekeeping(now: float) -> None:
    """Drop expired counters, then the oldest ones if the map is still too big.

    Called from :func:`record_failure` under the lock, every ``_SWEEP_EVERY``
    writes, so the cost is amortised to near nothing per call. Locked-out
    identities are never evicted: they are the only entries that do work.
    """
    for key, (count, window_start, locked_until) in list(_attempts.items()):
        if _expired(count, window_start, locked_until, now):
            _attempts.pop(key, None)
    if len(_attempts) <= _MAX_TRACKED:
        return
    live = [
        (key, window_start)
        for key, (count, window_start, locked_until) in _attempts.items()
        if locked_until <= now and count
    ]
    live.sort(key=lambda item: item[1])  # oldest window first
    for key, _ in live[: len(_attempts) - _MAX_TRACKED]:
        _attempts.pop(key, None)


def record_failure(ip: str, email: str) -> None:
    """Count a failed attempt; arm the lockout at the threshold."""
    global _writes_since_sweep
    key = _normalise_key(ip, email)
    now = time.time()
    with _lock:
        # Counted before the locked-identity shortcut below: a flood against an
        # already-locked account is exactly when the map needs sweeping, and it
        # is also when nothing else here would advance the counter.
        _writes_since_sweep += 1
        if _writes_since_sweep >= _SWEEP_EVERY:
            _writes_since_sweep = 0
            _housekeeping(now)
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
