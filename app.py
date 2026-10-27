import json
import os
import random
import tomllib

from flask import Flask, jsonify, render_template, request

import db
import engine

BASE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(BASE, "config.toml"), "rb") as f:
    CFG = tomllib.load(f)

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = False


def get_conn():
    return db.connect()


def error(msg, code=400):
    return jsonify({"error": msg}), code


def card_states(conn, where="archived=0", args=()):
    """Cartes avec statut calculé à la volée depuis answers."""
    cards = conn.execute(f"SELECT id, chapter, front, back FROM cards WHERE {where} ORDER BY id", args).fetchall()
    history = {}
    for r in conn.execute("SELECT card_id, session_id, correct FROM answers ORDER BY id"):
        history.setdefault(r["card_id"], []).append((r["session_id"], bool(r["correct"])))
    out = []
    for c in cards:
        info = engine.replay(history.get(c["id"], []), CFG)
        out.append({"id": c["id"], "chapter": c["chapter"], "front": c["front"], "back": c["back"],
                    "status": info["status"], "misses": info["misses"]})
    return out


def session_row(conn, sid):
    return conn.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()


def session_state(conn, row):
    q = json.loads(row["queue"])
    total = q["total"]
    state = {"id": row["id"], "validated": len(q["validated"]), "total": total,
             "finished": row["ended_at"] is not None, "end_reason": row["end_reason"], "card": None}
    if not state["finished"] and q["queue"]:
        c = conn.execute("SELECT id, chapter, front, back FROM cards WHERE id=?", (q["queue"][0],)).fetchone()
        state["card"] = dict(c)
    return state


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/home")
def api_home():
    conn = get_conn()
    states = card_states(conn)
    chapters = {}
    for c in states:
        ch = chapters.setdefault(c["chapter"], {"chapter": c["chapter"], "total": 0,
                                                **{s: 0 for s in (engine.NEW, engine.LEARNING,
                                                                  engine.VALIDATED, engine.ACQUIRED)}})
        ch["total"] += 1
        ch[c["status"]] += 1
    missed = sorted((c for c in states if c["misses"] > 0), key=lambda c: -c["misses"])[:10]
    open_row = conn.execute("SELECT * FROM sessions WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1").fetchone()
    open_session = None
    if open_row:
        q = json.loads(open_row["queue"])
        open_session = {"id": open_row["id"], "validated": len(q["validated"]), "total": q["total"]}
    abbreviations = sum(1 for c in states if engine.is_abbreviation(c["id"]))
    return jsonify({"chapters": list(chapters.values()), "abbreviations": abbreviations,
                    "missed": [{"id": c["id"], "chapter": c["chapter"], "front": c["front"],
                                "misses": c["misses"], "status": c["status"]} for c in missed],
                    "open_session": open_session})


@app.post("/api/sessions")
def api_start():
    body = request.get_json(silent=True) or {}
    chapters = body.get("chapters") or []
    include_acquired = bool(body.get("include_acquired"))
    only_abbreviations = bool(body.get("only_abbreviations"))
    review_acquired = bool(body.get("review_acquired"))
    if not isinstance(chapters, list) or not all(isinstance(c, str) for c in chapters):
        return error("chapters doit être une liste de chaînes")
    conn = get_conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        states = card_states(conn)
        if chapters:
            states = [c for c in states if c["chapter"] in chapters]
        if only_abbreviations:
            states = [c for c in states if engine.is_abbreviation(c["id"])]
        if review_acquired:
            include_acquired = True
            ids = engine.select_acquired(states, random.Random())
        else:
            ids = engine.select_cards(states, CFG, include_acquired, random.Random())
        if not ids:
            conn.execute("ROLLBACK")
            return error("aucune carte à réviser avec ces critères", 409)
        now = db.now()
        conn.execute("UPDATE sessions SET ended_at=?, end_reason='superseded' WHERE ended_at IS NULL", (now,))
        easy = [c["id"] for c in states if c["status"] == engine.VALIDATED]
        queue = engine.new_queue(ids, easy)
        queue["total"] = len(ids)
        cur = conn.execute("INSERT INTO sessions(started_at, chapters, include_acquired, queue) VALUES (?,?,?,?)",
                           (now, json.dumps(chapters), int(include_acquired), json.dumps(queue)))
        sid = cur.lastrowid
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return jsonify(session_state(conn, session_row(conn, sid))), 201


@app.get("/api/sessions/<int:sid>")
def api_session(sid):
    conn = get_conn()
    row = session_row(conn, sid)
    if not row:
        return error("session inconnue", 404)
    return jsonify(session_state(conn, row))


@app.post("/api/sessions/<int:sid>/answer")
def api_answer(sid):
    body = request.get_json(silent=True) or {}
    card_id, correct = body.get("card_id"), body.get("correct")
    if not isinstance(card_id, str) or not isinstance(correct, bool):
        return error("card_id (chaîne) et correct (booléen) requis")
    conn = get_conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = session_row(conn, sid)
        if not row:
            conn.execute("ROLLBACK")
            return error("session inconnue", 404)
        if row["ended_at"]:
            conn.execute("ROLLBACK")
            return error("session terminée", 409)
        queue = json.loads(row["queue"])
        try:
            new_queue, event = engine.apply_answer(queue, card_id, correct, CFG)
        except ValueError:
            conn.execute("ROLLBACK")
            return error("ce n'est pas la carte courante", 409)
        new_queue["total"] = queue["total"]
        now = db.now()
        conn.execute("INSERT INTO answers(card_id, session_id, mode, correct, answered_at) VALUES (?,?,?,?,?)",
                     (card_id, sid, "cards", int(correct), now))
        if new_queue["queue"]:
            conn.execute("UPDATE sessions SET queue=? WHERE id=?", (json.dumps(new_queue), sid))
        else:
            conn.execute("UPDATE sessions SET queue=?, ended_at=?, end_reason='done' WHERE id=?",
                         (json.dumps(new_queue), now, sid))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    state = session_state(conn, session_row(conn, sid))
    state["event"] = event
    return jsonify(state)


@app.post("/api/sessions/<int:sid>/end")
def api_end(sid):
    conn = get_conn()
    conn.execute("BEGIN IMMEDIATE")
    row = session_row(conn, sid)
    if not row:
        conn.execute("ROLLBACK")
        return error("session inconnue", 404)
    if not row["ended_at"]:
        conn.execute("UPDATE sessions SET ended_at=?, end_reason='manual' WHERE id=?", (db.now(), sid))
    conn.execute("COMMIT")
    return jsonify(session_state(conn, session_row(conn, sid)))


@app.get("/api/sessions/<int:sid>/summary")
def api_summary(sid):
    conn = get_conn()
    row = session_row(conn, sid)
    if not row:
        return error("session inconnue", 404)
    q = json.loads(row["queue"])
    answers = conn.execute("SELECT card_id, correct FROM answers WHERE session_id=? ORDER BY id", (sid,)).fetchall()
    n_correct = sum(a["correct"] for a in answers)
    to_review = list(dict.fromkeys(q["queue"] + [a["card_id"] for a in answers if not a["correct"]]))

    def fronts(ids):
        out = []
        for i in ids:
            c = conn.execute("SELECT id, chapter, front FROM cards WHERE id=?", (i,)).fetchone()
            if c:
                out.append(dict(c))
        return out

    newly_acquired = []
    for cid in q["validated"]:
        hist = [(r["session_id"], bool(r["correct"])) for r in conn.execute(
            "SELECT session_id, correct FROM answers WHERE card_id=? ORDER BY id", (cid,))]
        upto = [h for h in hist if h[0] <= sid]
        before = [h for h in upto if h[0] != sid]
        if (engine.compute_status(upto, CFG) == engine.ACQUIRED
                and engine.compute_status(before, CFG) != engine.ACQUIRED):
            newly_acquired.append(cid)
    return jsonify({"id": sid, "finished": row["ended_at"] is not None, "end_reason": row["end_reason"],
                    "total": q["total"], "validated": fronts(q["validated"]),
                    "answers": len(answers), "correct": n_correct,
                    "success_rate": round(100 * n_correct / len(answers)) if answers else None,
                    "to_review": fronts(to_review), "newly_acquired": fronts(newly_acquired)})


if __name__ == "__main__":
    app.run(host=os.environ.get("MEMO_HOST", "127.0.0.1"),
            port=int(os.environ.get("MEMO_PORT", "5005")), threaded=True)
