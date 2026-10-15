"""What the learned-vocabulary store accepts, refuses and interpolates.

The store is the half of self-learning that persists, and its rules are the
reason a taught entry can be trusted on the next spoken line: concepts are
constrained to the nine the pipeline maps, phrases are normalised and unique per
clinician, suppression patterns are validated before they are stored (an invalid
one must never reach extraction), and both lists are capped so a client bug
cannot fill the database.

Every case runs against a database of its own. The store reads its path once, at
import, and another module in a full run has usually imported it first — so a
test that relied on the environment variable would quietly write into the
clinician's real learned vocabulary and then read the previous run's leftovers
back, which is how a passing suite fails the second time it is run.

Runnable via pytest and directly
(``python backend/test_learned_vocabulary.py``).
"""

import os
import sys
import tempfile

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault(
    "PULSEIQ_LEARNED_DB", os.path.join(tempfile.mkdtemp(prefix="pulseiq-lv-test-"), "learned.db")
)

import pytest  # noqa: E402

from backend import learned_vocabulary as lv  # noqa: E402


@pytest.fixture(autouse=True)
def _private_store(tmp_path, monkeypatch):
    """A throwaway database per case, whatever the import order was."""
    monkeypatch.setattr(lv, "_DB_PATH", str(tmp_path / "learned-vocabulary.db"))
    monkeypatch.setattr(lv, "_initialised", False)
    yield


def test_a_phrase_is_normalised_and_taught_once():
    first = lv.teach_phrase(1, "Chest pain", "  Seena   DUKHTA hai ")
    assert first["created"] is True
    assert first["concept"] == "chest pain"
    assert first["phrase"] == "seena dukhta hai"
    again = lv.teach_phrase(1, "chest pain", "seena dukhta hai")
    assert again["created"] is False
    assert again["id"] == first["id"]
    assert len(lv.list_vocabulary(1)["phrases"]) == 1


def test_only_the_known_concepts_can_be_taught():
    with pytest.raises(ValueError) as failure:
        lv.teach_phrase(1, "left big toe pain", "anything")
    assert "Unknown concept" in str(failure.value)


def test_an_invalid_suppression_pattern_is_never_stored():
    with pytest.raises(ValueError) as failure:
        lv.teach_suppression(1, "no (chest")
    assert "regular expression" in str(failure.value)
    assert lv.list_vocabulary(1)["suppressions"] == []


def test_stored_suppressions_are_live_and_isolated():
    lv.teach_suppression(1, r"no\s+chest\s+pain", "negation phrasing")
    overlay = lv.overlay_for(1)
    assert [pattern.pattern for pattern in overlay["suppressions"]] == [r"no\s+chest\s+pain"]
    # Another clinician has none of it.
    other = lv.overlay_for(2)
    assert other["suppressions"] == []
    assert other["phrases"] == {}


def test_both_lists_are_capped():
    for index in range(lv._MAX_SUPPRESSIONS_PER_OWNER):
        lv.teach_suppression(3, rf"taught\s+phrase\s+{index}")
    with pytest.raises(ValueError) as failure:
        lv.teach_suppression(3, r"one\s+too\s+many")
    assert "full" in str(failure.value)
    assert len(lv.list_vocabulary(3)["suppressions"]) == lv._MAX_SUPPRESSIONS_PER_OWNER
    # Forgetting one makes room again, so the cap is a brake and not a dead end.
    assert lv.clear_all(3) == lv._MAX_SUPPRESSIONS_PER_OWNER
    lv.teach_suppression(3, r"one\s+too\s+many")


def test_every_write_moves_the_generation_the_overlay_watches():
    before = lv.get_generation()
    taught = lv.teach_phrase(4, "fatigue", "sust kamzori")
    assert lv.get_generation() > before
    assert lv.overlay_for(4)["generation"] == lv.get_generation()
    assert lv.forget_phrase(4, taught["id"]) is True
    assert lv.forget_phrase(4, taught["id"]) is False


if __name__ == "__main__":  # pragma: no cover - manual run convenience
    raise SystemExit(pytest.main([__file__, "-q"]))
