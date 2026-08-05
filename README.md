# Tic Tac Toe Online

A web-based Tic Tac Toe game: play against an AI opponent or a friend on the
same device, with lightweight name+PIN profiles and (eventually) a global
leaderboard. See `docs/PRD.md` for requirements and `docs/DESIGN.md` for the
full technical design.

**Current build status:** this is an in-progress slice of the full design --
profile creation/sign-in (name + PIN) and a full game against the AI (Easy,
Medium, or Hard) work end to end. Human-vs-human, the stats page, and the
leaderboard are designed (see DESIGN.md) but not implemented yet.

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Run locally

```bash
.venv/bin/uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000/ in a browser.

## Database: local fallback vs. Turso

`docs/DESIGN.md` specifies a managed **Turso** (libSQL) database for durable
data (profiles, sessions, game history), reached via two environment
variables: `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN`. Nobody has created
the actual Turso account/database yet -- that happens later, at deploy time.

So that the app is runnable locally (and by QA) without any external
account, `app/db.py` falls back to a **local libSQL/SQLite file**
(`local.db`, created in the project root) whenever `TURSO_DATABASE_URL` is
not set in the environment:

- **No `TURSO_DATABASE_URL` env var set** (the default for local dev): the
  app opens/creates `local.db` in the project root. This file is
  git-ignored -- each developer/QA run gets its own local database, and it's
  safe to delete at any time to reset all data.
- **`TURSO_DATABASE_URL` (and, if required, `TURSO_AUTH_TOKEN`) set**: the
  app connects to that real Turso database instead, over the network.

This is a single conditional in `app/db.py`'s `get_connection()` function --
the `libsql` Python package exposes the same connection interface for a
local file URL (`file:local.db`) and a remote `libsql://...` URL, so no
other code (routes, schema, queries) needs to know or care which one is in
use.

To point the app at a real Turso database once one exists:

```bash
export TURSO_DATABASE_URL="libsql://<your-db>.turso.io"
export TURSO_AUTH_TOKEN="<your-token>"
.venv/bin/uvicorn app.main:app --reload
```
