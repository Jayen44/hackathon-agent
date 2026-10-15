"""SQLite persistence so the agent survives restarts."""
import json
import sqlite3
from pathlib import Path

DB_PATH = Path("agent_state.db")


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS events ("
        "id INTEGER PRIMARY KEY, tick INTEGER, kind TEXT, payload TEXT)"
    )
    conn.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT)")
    return conn


def log_event(conn: sqlite3.Connection, tick: int, kind: str, payload: dict) -> None:
    conn.execute(
        "INSERT INTO events (tick, kind, payload) VALUES (?, ?, ?)",
        (tick, kind, json.dumps(payload)),
    )
    conn.commit()


def get_state(conn: sqlite3.Connection, key: str, default=None):
    row = conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def set_state(conn: sqlite3.Connection, key: str, value) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)", (key, json.dumps(value))
    )
    conn.commit()
