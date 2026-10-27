import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import (ACQUIRED, LEARNING, NEW, VALIDATED, apply_answer,
                    compute_status, new_queue, select_cards)

CFG = dict(session_good_answers=3, sessions_to_acquire=2, max_cards_per_session=15,
           new_per_session=5, retry_offset=3)


def test_three_good_answers_validate():
    assert compute_status([], CFG) == NEW
    assert compute_status([(1, True), (1, True)], CFG) == LEARNING
    assert compute_status([(1, True)] * 3, CFG) == VALIDATED


def test_error_resets_counter():
    assert compute_status([(1, True), (1, True), (1, False), (1, True)], CFG) == LEARNING
    assert compute_status([(1, True), (1, True), (1, False)] + [(1, True)] * 3, CFG) == VALIDATED


def test_two_sessions_acquire():
    assert compute_status([(1, True)] * 3 + [(2, True)] * 3, CFG) == ACQUIRED
    # deux séries dans la même session ne comptent qu'une validation
    assert compute_status([(1, True)] * 3 + [(1, False)] + [(1, True)] * 3, CFG) == VALIDATED


def test_acquired_card_demoted_on_error():
    base = [(1, True)] * 3 + [(2, True)] * 3
    assert compute_status(base + [(3, False)], CFG) == LEARNING
    # il faut de nouveau 2 sessions
    assert compute_status(base + [(3, False)] + [(3, True)] * 3, CFG) == VALIDATED


def test_error_on_once_validated_keeps_validation():
    assert compute_status([(1, True)] * 3 + [(2, False)], CFG) == VALIDATED


def cards(n_new=0, n_learning=0, n_validated=0, n_acquired=0):
    out = []
    for status, n in ((NEW, n_new), (LEARNING, n_learning), (VALIDATED, n_validated), (ACQUIRED, n_acquired)):
        out += [{"id": f"{status}{i}", "status": status, "misses": i} for i in range(n)]
    return out


def test_caps_15_cards_and_5_new():
    ids = select_cards(cards(n_new=30), CFG, False, random.Random(0))
    assert len(ids) == 5
    ids = select_cards(cards(n_new=30, n_learning=20), CFG, False, random.Random(0))
    assert len(ids) == 15 and len(set(ids)) == 15
    assert sum(i.startswith(NEW) for i in ids) == 0
    ids = select_cards(cards(n_new=30, n_learning=8, n_validated=4), CFG, False, random.Random(0))
    assert len(ids) == 15 and sum(i.startswith(NEW) for i in ids) == 3


def test_priority_and_acquired_option():
    pool = cards(n_new=3, n_learning=3, n_validated=2, n_acquired=4)
    ids = select_cards(pool, CFG, False, random.Random(1))
    assert len(ids) == 8
    assert ids[:3] == ["en_apprentissage2", "en_apprentissage1", "en_apprentissage0"]  # plus ratées d'abord
    assert not any(i.startswith(ACQUIRED) for i in ids)
    ids = select_cards(pool, CFG, True, random.Random(1))
    assert len(ids) == 12 and all(i.startswith(ACQUIRED) for i in ids[8:])


def test_failed_card_reinserted_at_offset():
    q = new_queue(list("abcdef"))
    q, event = apply_answer(q, "a", False, CFG)
    assert q["queue"] == list("bcdaef") and event is None
    short, _ = apply_answer(new_queue(list("ab")), "a", False, CFG)
    assert short["queue"] == list("ba")


def test_good_answer_goes_to_end_then_validates():
    q = new_queue(list("ab"))
    q, e1 = apply_answer(q, "a", True, CFG)
    assert q["queue"] == list("ba") and e1 is None
    q, _ = apply_answer(q, "b", True, CFG)
    q, _ = apply_answer(q, "a", True, CFG)
    q, _ = apply_answer(q, "b", True, CFG)
    q, event = apply_answer(q, "a", True, CFG)
    assert event == "validated" and q["validated"] == ["a"] and q["queue"] == ["b"]


def test_not_current_card_rejected():
    import pytest
    with pytest.raises(ValueError):
        apply_answer(new_queue(list("ab")), "b", True, CFG)
