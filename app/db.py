"""
Database connection helper (Turso / libSQL) + schema initialization.

Design (docs/DESIGN.md, Section 3 & 8):
    The app talks to a SQLite-dialect database over the `libsql` client
    library. In production that database is a managed Turso instance,
    reached via TURSO_DATABASE_URL ("libsql://...turso.io") and
    TURSO_AUTH_TOKEN.

Local-dev fallback (not in DESIGN.md, added for this build so the app is
runnable without a Turso account):
    If TURSO_DATABASE_URL is not set in the environment, db.py falls back
    to a local libSQL file (`file:local.db`, no auth token) instead of a
    remote Turso database. The `libsql` client exposes the same connect()
    interface for both a local file URL and a remote libsql:// URL, so
    this is a single small conditional right here rather than two
    parallel code paths. See README.md for more detail.
"""

import os
from pathlib import Path

import libsql

# Local dev DB file lives at the project root (next to requirements.txt).
_LOCAL_DB_PATH = Path(__file__).resolve().parent.parent / "local.db"

TURSO_DATABASE_URL = os.environ.get("TURSO_DATABASE_URL")
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN")

SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS profiles (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        display_name  TEXT NOT NULL COLLATE NOCASE UNIQUE,
        pin_hash      TEXT NOT NULL,
        pin_salt      TEXT NOT NULL,
        wins          INTEGER NOT NULL DEFAULT 0,
        losses        INTEGER NOT NULL DEFAULT 0,
        ties          INTEGER NOT NULL DEFAULT 0,
        created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        token         TEXT PRIMARY KEY,
        profile_id    INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
        created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS game_results (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        mode          TEXT NOT NULL CHECK (mode IN ('ai','human')),
        difficulty    TEXT CHECK (difficulty IN ('easy','medium','hard')),
        x_profile_id  INTEGER NOT NULL REFERENCES profiles(id),
        o_profile_id  INTEGER REFERENCES profiles(id),
        result        TEXT NOT NULL CHECK (result IN ('x_won','o_won','tie')),
        played_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_game_results_x ON game_results(x_profile_id)",
    "CREATE INDEX IF NOT EXISTS idx_game_results_o ON game_results(o_profile_id)",
]


def get_connection():
    """
    Return a libsql connection.

    - If TURSO_DATABASE_URL is set: connect to the real Turso database
      (with TURSO_AUTH_TOKEN, if also set).
    - Otherwise: connect to a local libSQL/SQLite file so the app runs
      fully offline for local dev / QA, no external account needed.
    """
    if TURSO_DATABASE_URL:
        if TURSO_AUTH_TOKEN:
            return libsql.connect(TURSO_DATABASE_URL, auth_token=TURSO_AUTH_TOKEN)
        return libsql.connect(TURSO_DATABASE_URL)
    return libsql.connect(f"file:{_LOCAL_DB_PATH}")


# A single module-level connection, reused for the lifetime of the process.
# This mirrors the single-process/single-worker constraint already required
# by the in-memory active_games dict (DESIGN.md Section 1/9).
_connection = None


def get_conn():
    global _connection
    if _connection is None:
        _connection = get_connection()
        init_db(_connection)
    return _connection


def init_db(conn=None):
    """Create tables/indexes if they don't already exist. Idempotent."""
    owns_conn = conn is None
    if conn is None:
        conn = get_connection()
    for stmt in SCHEMA_STATEMENTS:
        conn.execute(stmt)
    conn.commit()
    return conn if owns_conn else None


def execute(sql: str, params=()):
    """Execute a statement against the shared connection and commit."""
    conn = get_conn()
    cur = conn.execute(sql, params)
    conn.commit()
    return cur


def query(sql: str, params=()):
    """Execute a SELECT and return all rows."""
    conn = get_conn()
    cur = conn.execute(sql, params)
    return cur.fetchall()


def query_one(sql: str, params=()):
    rows = query(sql, params)
    return rows[0] if rows else None


def query_dicts(sql: str, params=()):
    """Execute a SELECT and return rows as a list of dicts (column name -> value)."""
    conn = get_conn()
    cur = conn.execute(sql, params)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def query_one_dict(sql: str, params=()):
    rows = query_dicts(sql, params)
    return rows[0] if rows else None
