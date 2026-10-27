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
    missed_in = set()
    misses = 0
    for session_id, correct in answers:
        if correct:
            counters[session_id] = counters.get(session_id, 0) + 1
            # Carte déjà validée (pas encore acquise), réussie du premier coup dans la session : 1 bonne réponse suffit.
            easy = 0 < len(validated) < needed and session_id not in missed_in
            if counters[session_id] >= (1 if easy else good) and session_id not in validated:
                validated.append(session_id)
        else:
            misses += 1
            missed_in.add(session_id)
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


def is_abbreviation(card_id):
    """Convention d'id : les cartes « Que signifie X ? » ont un segment `.abbr-` (ex. cefi2.p1-couts.abbr-cv)."""
    return ".abbr-" in card_id


def quotas(total, cfg):
    """Répartit `total` places entre les statuts selon les ratios de la config (plus fort reste)."""
    ratios = {NEW: cfg["ratio_new"], ACQUIRED: cfg["ratio_acquired"],
              VALIDATED: cfg["ratio_validated"], LEARNING: cfg["ratio_learning"]}
    out = {s: int(total * r) for s, r in ratios.items()}
    order = sorted(ratios, key=lambda s: -(total * ratios[s] - out[s]))
    for s in order[:max(0, total - sum(out.values()))]:
        out[s] += 1
    return out


def select_cards(cards_with_status, cfg, include_acquired, rng):
    """cards_with_status : [{"id", "status", "misses"}]. Renvoie les ids retenus.

    Une session vise le mélange des ratios (nouvelles / acquises / validées / en apprentissage) ;
    une catégorie trop courte est complétée par les autres (nouvelles, apprentissage, validées, puis
    acquises seulement si include_acquired).
    """
    def shuffled(items):
        items = list(items)
        rng.shuffle(items)
        return items

    by_status = {s: [c for c in cards_with_status if c["status"] == s]
                 for s in (LEARNING, VALIDATED, NEW, ACQUIRED)}
    pools = {LEARNING: sorted(shuffled(by_status[LEARNING]), key=lambda c: -c["misses"]),
             VALIDATED: shuffled(by_status[VALIDATED]),
             NEW: shuffled(by_status[NEW]),
             ACQUIRED: shuffled(by_status[ACQUIRED])}
    total = cfg["max_cards_per_session"]
    chosen = []
    for status, quota in quotas(total, cfg).items():
        chosen.extend(c["id"] for c in pools[status][:quota])
        pools[status] = pools[status][quota:]
    for status in (NEW, LEARNING, VALIDATED) + ((ACQUIRED,) if include_acquired else ()):
        room = total - len(chosen)
        chosen.extend(c["id"] for c in pools[status][:room])
    return chosen


def new_queue(card_ids, easy_ids=()):
    """easy_ids : cartes déjà validées, qui n'ont besoin que d'une bonne réponse si réussies du premier coup."""
    ids = list(card_ids)
    return {"queue": ids, "counts": {i: 0 for i in ids}, "validated": [],
            "easy": [i for i in ids if i in set(easy_ids)], "missed": []}


def apply_answer(queue, card_id, correct, cfg):
    """Renvoie (nouvelle file, événement). L'événement vaut "validated" ou None."""
    if not queue["queue"] or queue["queue"][0] != card_id:
        raise ValueError("ce n'est pas la carte courante")
    q = copy.deepcopy(queue)
    q["queue"].pop(0)
    event = None
    if correct:
        q["counts"][card_id] = q["counts"].get(card_id, 0) + 1
        easy = card_id in q.get("easy", []) and card_id not in q.get("missed", [])
        if q["counts"][card_id] >= (1 if easy else cfg["session_good_answers"]):
            q["validated"].append(card_id)
            event = "validated"
        else:
            q["queue"].append(card_id)
    else:
        q["counts"][card_id] = 0
        q.setdefault("missed", []).append(card_id)
        q["queue"].insert(min(cfg["retry_offset"], len(q["queue"])), card_id)
    return q, event
