"""Règles d'acquisition : fonctions pures, sans I/O, sans Flask."""
import copy

NEW = "nouvelle"
LEARNING = "en_apprentissage"
VALIDATED = "validee"
ACQUIRED = "acquise"


def replay(answers, cfg):
    """Rejoue les réponses d'une carte [(session_id, correct), ...] dans l'ordre.

    Renvoie {"status", "misses", "validated_sessions"}.
    """
    good = cfg["session_good_answers"]
    needed = cfg["sessions_to_acquire"]
    counters = {}
    validated = []
    misses = 0
    for session_id, correct in answers:
        if correct:
            counters[session_id] = counters.get(session_id, 0) + 1
            if counters[session_id] >= good and session_id not in validated:
                validated.append(session_id)
        else:
            misses += 1
            counters[session_id] = 0
            if len(validated) >= needed:
                validated = []
    if not answers:
        status = NEW
    elif len(validated) >= needed:
        status = ACQUIRED
    elif validated:
        status = VALIDATED
    else:
        status = LEARNING
    return {"status": status, "misses": misses, "validated_sessions": validated}


def compute_status(answers, cfg):
    return replay(answers, cfg)["status"]


def select_cards(cards_with_status, cfg, include_acquired, rng):
    """cards_with_status : [{"id", "status", "misses"}]. Renvoie les ids retenus, par priorité."""
    def shuffled(items):
        items = list(items)
        rng.shuffle(items)
        return items

    by_status = {s: [c for c in cards_with_status if c["status"] == s]
                 for s in (LEARNING, VALIDATED, NEW, ACQUIRED)}
    learning = sorted(shuffled(by_status[LEARNING]), key=lambda c: -c["misses"])
    validated = shuffled(by_status[VALIDATED])
    new = shuffled(by_status[NEW])[:cfg["new_per_session"]]
    acquired = shuffled(by_status[ACQUIRED]) if include_acquired else []

    chosen = []
    for group in (learning, validated, new, acquired):
        chosen.extend(c["id"] for c in group)
    return chosen[:cfg["max_cards_per_session"]]


def new_queue(card_ids):
    ids = list(card_ids)
    return {"queue": ids, "counts": {i: 0 for i in ids}, "validated": []}


def apply_answer(queue, card_id, correct, cfg):
    """Renvoie (nouvelle file, événement). L'événement vaut "validated" ou None."""
    if not queue["queue"] or queue["queue"][0] != card_id:
        raise ValueError("ce n'est pas la carte courante")
    q = copy.deepcopy(queue)
    q["queue"].pop(0)
    event = None
    if correct:
        q["counts"][card_id] = q["counts"].get(card_id, 0) + 1
        if q["counts"][card_id] >= cfg["session_good_answers"]:
            q["validated"].append(card_id)
            event = "validated"
        else:
            q["queue"].append(card_id)
    else:
        q["counts"][card_id] = 0
        q["queue"].insert(min(cfg["retry_offset"], len(q["queue"])), card_id)
    return q, event
