"""What the learned-vocabulary store accepts, refuses and interpolates.

The store is the half of self-learning that persists, and its rules are the
reason a taught entry can be trusted on the next spoken line: concepts are
constrained to the nine the pipeline maps, phrases are normalised and unique per
clinician, suppression patterns are validated before they are stored (an invalid
one must never reach extraction), and both lists are capped so a client bug
cannot fill the database. Each case below pins one of those rules, and each uses
its own owner id so nothing here can see another test's entries.

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

from backend import learned_vocabulary as lv  # noqa: E402


def test_a_phrase_is_normalised_and_taught_once():
    owner = 900_001
    first = lv.teach_phrase(owner, "Chest pain", "  Seena   DUKHTA hai ")
    assert first["created"] is True
    assert first["concept"] == "chest pain"
    assert first["phrase"] == "seena dukhta hai"
    again = lv.teach_phrase(owner, "chest pain", "seena dukhta hai")
    assert again["created"] is False
    assert again["id"] == first["id"]
    assert len(lv.list_vocabulary(owner)["phrases"]) == 1


def test_only_the_known_concepts_can_be_taught():
    try:
        lv.teach_phrase(900_002, "left big toe pain", "anything")
    except ValueError as exc:
        assert "Unknown concept" in str(exc)
    else:  # pragma: no cover - the concept is outside the pipeline by construction
        raise AssertionError("an unknown concept must be refused")


def test_an_invalid_suppression_pattern_is_never_stored():
    owner = 900_003
    try:
        lv.teach_suppression(owner, "no (chest")
    except ValueError as exc:
        assert "regular expression" in str(exc)
    else:  # pragma: no cover - the pattern cannot compile
        raise AssertionError("an invalid regex must be refused")
    assert lv.list_vocabulary(owner)["suppressions"] == []


def test_stored_suppressions_are_live_and_isolated():
    owner = 900_004
    lv.teach_suppression(owner, r"no\s+chest\s+pain", "negation phrasing")
    overlay = lv.overlay_for(owner)
    assert [pattern.pattern for pattern in overlay["suppressions"]] == [r"no\s+chest\s+pain"]
    # Another clinician has none of it.
    other = lv.overlay_for(900_005)
    assert other["suppressions"] == []
    assert other["phrases"] == {}


def test_both_lists_are_capped():
    owner = 900_006
    for index in range(lv._MAX_SUPPRESSIONS_PER_OWNER):
        lv.teach_suppression(owner, rf"taught\s+phrase\s+{index}")
    try:
        lv.teach_suppression(owner, r"one\s+too\s+many")
    except ValueError as exc:
        assert "full" in str(exc)
    else:  # pragma: no cover - the cap is reached above
        raise AssertionError("the suppression list must be capped")
    assert len(lv.list_vocabulary(owner)["suppressions"]) == lv._MAX_SUPPRESSIONS_PER_OWNER
    # Forgetting one makes room again, so the cap is a brake and not a dead end.
    removed = lv.clear_all(owner)
    assert removed == lv._MAX_SUPPRESSIONS_PER_OWNER
    lv.teach_suppression(owner, r"one\s+too\s+many")


def test_every_write_moves_the_generation_the_overlay_watches():
    owner = 900_007
    before = lv.get_generation()
    taught = lv.teach_phrase(owner, "fatigue", "sust kamzori")
    assert lv.get_generation() > before
    assert lv.overlay_for(owner)["generation"] == lv.get_generation()
    assert lv.forget_phrase(owner, taught["id"]) is True
    assert lv.forget_phrase(owner, taught["id"]) is False


if __name__ == "__main__":  # pragma: no cover - manual run convenience
    for _name, _case in sorted(globals().items()):
        if _name.startswith("test_") and callable(_case):
            _case()
            print(f"[PASS] {_name}")
    print("learned vocabulary: ok")
