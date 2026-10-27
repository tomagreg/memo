import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import (ACQUIRED, LEARNING, NEW, VALIDATED, apply_answer,
                    compute_status, new_queue, select_cards)

CFG = dict(session_good_answers=2, sessions_to_acquire=2, max_cards_per_session=15,
           ratio_new=0.70, ratio_acquired=0.15, ratio_validated=0.05, ratio_learning=0.10,
           retry_offset=3)


def test_two_good_answers_validate():
    assert compute_status([], CFG) == NEW
    assert compute_status([(1, True)], CFG) == LEARNING
    assert compute_status([(1, True)] * 2, CFG) == VALIDATED


def test_error_resets_counter():
    assert compute_status([(1, True), (1, False), (1, True)], CFG) == LEARNING
    assert compute_status([(1, True), (1, False)] + [(1, True)] * 2, CFG) == VALIDATED


def test_two_sessions_acquire():
    assert compute_status([(1, True)] * 2 + [(2, True)] * 2, CFG) == ACQUIRED
    # deux séries dans la même session ne comptent qu'une validation
    assert compute_status([(1, True)] * 2 + [(1, False)] + [(1, True)] * 2, CFG) == VALIDATED


def test_acquired_card_demoted_on_error():
    base = [(1, True)] * 2 + [(2, True)] * 2
    assert compute_status(base + [(3, False)], CFG) == LEARNING
    # il faut de nouveau 2 sessions
    assert compute_status(base + [(3, False)] + [(3, True)] * 2, CFG) == VALIDATED


def test_error_on_once_validated_keeps_validation():
    assert compute_status([(1, True)] * 2 + [(2, False)], CFG) == VALIDATED


def cards(n_new=0, n_learning=0, n_validated=0, n_acquired=0):
    out = []
    for status, n in ((NEW, n_new), (LEARNING, n_learning), (VALIDATED, n_validated), (ACQUIRED, n_acquired)):
        out += [{"id": f"{status}{i}", "status": status, "misses": i} for i in range(n)]
    return out


def count(ids, status):
    return sum(i.startswith(status) for i in ids)


def test_mix_70_15_5_10():
    pool = cards(n_new=40, n_learning=10, n_validated=10, n_acquired=10)
    ids = select_cards(pool, CFG, False, random.Random(0))
    assert len(ids) == 15 and len(set(ids)) == 15
    assert (count(ids, NEW), count(ids, ACQUIRED), count(ids, VALIDATED), count(ids, LEARNING)) == (11, 2, 1, 1)  # 10,5 nouvelles arrondi au plus fort reste


def test_short_category_is_backfilled():
    ids = select_cards(cards(n_new=30), CFG, False, random.Random(0))
    assert len(ids) == 15 and count(ids, NEW) == 15
    ids = select_cards(cards(n_new=3, n_learning=3, n_validated=2, n_acquired=4), CFG, False, random.Random(1))
    # quotas 10/2/1/2 : nouvelles 3 (toutes), acquises 2, puis le reste complété par apprentissage et validées
    assert len(ids) == 10
    assert (count(ids, NEW), count(ids, ACQUIRED), count(ids, VALIDATED), count(ids, LEARNING)) == (3, 2, 2, 3)


def test_most_missed_learning_first_and_acquired_backfill_option():
    pool = cards(n_learning=5, n_acquired=12)
    ids = select_cards(pool, CFG, False, random.Random(1))
    # pas de nouvelles : l'apprentissage complète (5), les acquises restent à leur quota (2)
    assert count(ids, LEARNING) == 5 and count(ids, ACQUIRED) == 2 and len(ids) == 7
    ids = select_cards(cards(n_learning=30), CFG, False, random.Random(1))
    assert ids[:2] == ["en_apprentissage29", "en_apprentissage28"]  # plus ratées d'abord
    ids = select_cards(pool, CFG, True, random.Random(1))
    assert len(ids) == 15


def test_validated_card_needs_one_good_answer_if_first_try():
    q = new_queue(["a", "b"], easy_ids=["a"])
    q, ev = apply_answer(q, "a", True, CFG)
    assert ev == "validated" and q["queue"] == ["b"]
    q = new_queue(["a"], easy_ids=["a"])
    q, _ = apply_answer(q, "a", False, CFG)  # ratée : retour à la règle des 2 bonnes réponses consécutives
    q, ev = apply_answer(q, "a", True, CFG)
    assert ev is None and q["validated"] == []
    q, ev = apply_answer(q, "a", True, CFG)
    assert ev == "validated"


def test_consecutive_required_in_queue():
    q = new_queue(["a"])
    q, _ = apply_answer(q, "a", True, CFG)
    q, _ = apply_answer(q, "a", False, CFG)  # l'erreur remet le compteur à zéro
    q, ev = apply_answer(q, "a", True, CFG)
    assert ev is None
    q, ev = apply_answer(q, "a", True, CFG)
    assert ev == "validated"


def test_replay_matches_one_answer_rule():
    assert compute_status([(1, True)] * 2 + [(2, True)], CFG) == ACQUIRED
    assert compute_status([(1, True)] * 2 + [(2, False), (2, True)], CFG) == VALIDATED
    assert compute_status([(1, True)] * 2 + [(2, False)] + [(2, True)] * 2, CFG) == ACQUIRED
    assert compute_status([(1, True)], CFG) == "en_apprentissage"


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
    q, event = apply_answer(q, "a", True, CFG)
    assert event == "validated" and q["validated"] == ["a"] and q["queue"] == ["b"]


def test_not_current_card_rejected():
    import pytest
    with pytest.raises(ValueError):
        apply_answer(new_queue(list("ab")), "b", True, CFG)
