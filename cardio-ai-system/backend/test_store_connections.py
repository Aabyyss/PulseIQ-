"""Connection hygiene for the two local SQLite stores.

Both stores open a short-lived connection per call — accounts/sessions/history in
``auth_store``, learned vocabulary in ``learned_vocabulary``. ``with
sqlite3.connect(...) as conn`` commits the transaction but does not close the
handle, so only the garbage collector was releasing these; a server that answers
a request with five store calls was holding five file handles and five WAL
readers until a collection happened to run. Each call must now close what it
opened, which is what this module checks: it records every connection the stores
create and asserts that all of them are unusable by the time the call returns.

Both stores read their path once, at import, and in a full run another module has
usually imported them first — so setting the environment variable here is not
enough, and a case that relied on it would write test accounts and taught phrases
into the clinician's real databases. Each case redirects the stores at its own
throwaway file instead.

Runnable via pytest and directly
(``python backend/test_store_connections.py``).
"""

import os
import sqlite3
import sys
import tempfile

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault(
    "PULSEIQ_DB", os.path.join(tempfile.mkdtemp(prefix="pulseiq-store-test-"), "auth.db")
)

import pytest  # noqa: E402

from backend import auth_store, learned_vocabulary  # noqa: E402


@pytest.fixture(autouse=True)
def _private_stores(tmp_path, monkeypatch):
    """A throwaway pair of databases per case, whatever the import order was."""
    monkeypatch.setattr(auth_store, "_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setattr(auth_store, "_initialised", False)
    monkeypatch.setattr(learned_vocabulary, "_DB_PATH", str(tmp_path / "learned.db"))
    monkeypatch.setattr(learned_vocabulary, "_initialised", False)
    yield


class _Recorder:
    """Stand-in for ``sqlite3.connect`` that remembers what it handed out."""

    def __init__(self, module: object) -> None:
        self.module = module
        self.opened: list[sqlite3.Connection] = []
        self._real = module.sqlite3.connect

    def __enter__(self) -> "_Recorder":
        real = self._real

        def recording(*args, **kwargs):
            conn = real(*args, **kwargs)
            self.opened.append(conn)
            return conn

        self.module.sqlite3.connect = recording
        return self

    def __exit__(self, *exc) -> None:
        self.module.sqlite3.connect = self._real

    def closed(self) -> int:
        return sum(1 for conn in self.opened if _is_closed(conn))


def _is_closed(conn: sqlite3.Connection) -> bool:
    """A closed connection refuses work; that is the only reliable probe."""
    try:
        conn.execute("SELECT 1")
    except sqlite3.ProgrammingError:
        return True
    return False


def test_auth_store_calls_close_their_connections():
    user = auth_store.create_user("hygiene@cardio.local", "HygienePass123", "Hygiene")
    with _Recorder(auth_store) as recorder:
        auth_store.issue_token(user["id"])
        auth_store.verify_user("hygiene@cardio.local", "HygienePass123")
        auth_store.list_sessions(user["id"])
        auth_store.add_screening(user["id"], {"text": "chest pain", "probability": 0.4})
        auth_store.list_screenings(user["id"])
        auth_store.count_users()
        assert recorder.opened, "no connection was created — the test proves nothing"
        assert recorder.closed() == len(recorder.opened)


def test_learned_vocabulary_calls_close_their_connections():
    with _Recorder(learned_vocabulary) as recorder:
        learned_vocabulary.teach_phrase(7, "chest pain", "seena dukhta hai")
        learned_vocabulary.list_vocabulary(7)
        learned_vocabulary.overlay_for(7)
        learned_vocabulary.get_generation()
        assert recorder.opened, "no connection was created — the test proves nothing"
        assert recorder.closed() == len(recorder.opened)


def test_a_rejected_write_still_closes_its_connection():
    # The error path must release the handle too: a duplicate registration is
    # refused from inside the store's own connection block.
    auth_store.create_user("taken@cardio.local", "TakenPass123", "Taken")
    with _Recorder(auth_store) as recorder:
        try:
            auth_store.create_user("taken@cardio.local", "OtherPass123", "Other")
        except ValueError:
            pass
        else:  # pragma: no cover - the email is already registered above
            raise AssertionError("a duplicate email must be refused")
    assert recorder.opened, "no connection was created — the test proves nothing"
    assert recorder.closed() == len(recorder.opened)


if __name__ == "__main__":  # pragma: no cover - manual run convenience
    raise SystemExit(pytest.main([__file__, "-q"]))
