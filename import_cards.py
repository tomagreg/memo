"""python import_cards.py cards/cefi2.json [--db chemin]

Upsert par id. Ne touche jamais à answers ni à sessions, ne supprime rien.
"""
import argparse
import json
import sys

import db

REQUIRED = ("id", "chapter", "front", "back")


def load(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    errors = []
    if data.get("schema") != 1:
        errors.append("schema doit valoir 1")
    if not data.get("deck"):
        errors.append("champ deck manquant")
    cards = data.get("cards")
    if not isinstance(cards, list) or not cards:
        errors.append("cards doit être une liste non vide")
        cards = []
    seen = set()
    for i, c in enumerate(cards):
        for k in REQUIRED:
            if not isinstance(c.get(k), str) or not c[k].strip():
                errors.append(f"carte #{i} : champ « {k} » manquant ou vide")
        cid = c.get("id")
        if cid in seen:
            errors.append(f"id en double : {cid}")
        seen.add(cid)
    if errors:
        raise ValueError("\n".join(errors))
    return data


def import_cards(path, db_path=None):
    data = load(path)
    conn = db.connect(db_path)
    stats = {"créées": 0, "mises à jour": 0, "inchangées": 0, "absentes": 0}
    conn.execute("BEGIN IMMEDIATE")
    try:
        for c in data["cards"]:
            row = conn.execute("SELECT deck, chapter, front, back, archived FROM cards WHERE id=?",
                               (c["id"],)).fetchone()
            new = (data["deck"], c["chapter"], c["front"], c["back"], 0)
            if row is None:
                conn.execute("INSERT INTO cards(id, deck, chapter, front, back, archived, updated_at) "
                             "VALUES (?,?,?,?,?,0,?)", (c["id"], *new[:4], db.now()))
                stats["créées"] += 1
            elif tuple(row) != new:
                conn.execute("UPDATE cards SET deck=?, chapter=?, front=?, back=?, archived=0, updated_at=? "
                             "WHERE id=?", (*new[:4], db.now(), c["id"]))
                stats["mises à jour"] += 1
            else:
                stats["inchangées"] += 1
        ids = [c["id"] for c in data["cards"]]
        in_deck = [r["id"] for r in conn.execute("SELECT id FROM cards WHERE deck=?", (data["deck"],))]
        stats["absentes"] = len(set(in_deck) - set(ids))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return stats


def main():
    p = argparse.ArgumentParser()
    p.add_argument("file")
    p.add_argument("--db")
    args = p.parse_args()
    try:
        stats = import_cards(args.file, args.db)
    except (ValueError, OSError, json.JSONDecodeError) as e:
        print(f"Import refusé :\n{e}", file=sys.stderr)
        sys.exit(1)
    print(" / ".join(f"{k} : {v}" for k, v in stats.items()))


if __name__ == "__main__":
    main()
