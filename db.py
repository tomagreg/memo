import os
import sqlite3
from datetime import datetime, timezone

DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "memo.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS cards(
    id TEXT PRIMARY KEY, deck TEXT, chapter TEXT, front TEXT, back TEXT,
    archived INTEGER DEFAULT 0, updated_at TEXT);
CREATE TABLE IF NOT EXISTS sessions(
    id INTEGER PRIMARY KEY, started_at TEXT, ended_at TEXT NULL, end_reason TEXT NULL,
    chapters TEXT, include_acquired INTEGER, queue TEXT);
CREATE TABLE IF NOT EXISTS answers(
    id INTEGER PRIMARY KEY, card_id TEXT, session_id INTEGER, mode TEXT DEFAULT 'cards',
    correct INTEGER, answered_at TEXT);
CREATE INDEX IF NOT EXISTS answers_card ON answers(card_id, id);
CREATE INDEX IF NOT EXISTS answers_session ON answers(session_id);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path=None):
    path = path or os.environ.get("MEMO_DB") or DEFAULT_DB
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn
