# Tic Tac Toe Online

A web-based Tic Tac Toe game: play against an AI opponent (Easy/Medium/Hard)
or a friend on the same device, with lightweight name+PIN profiles, personal
stats, a global leaderboard, and self-service PIN recovery via email. See
`docs/PRD.md`/`docs/DESIGN.md` for the v1 design and `docs/PRD_V2.md`/
`docs/DESIGN_V2.md` for the v2 additions (PIN recovery, real-time
cross-device play, UI overhaul).

**Live:** https://tic-tac-toe-online-jlxa.onrender.com/ (free tier -- may
take up to ~60s to wake up if nobody's visited in the last 15 minutes).

**Current build status:** v1 and v2 are both fully implemented and deployed
-- AI play (Easy/Medium/Hard), local and real-time cross-device
human-vs-human, profiles with PIN recovery, stats, a leaderboard, and a
full visual/responsive UI pass. See `docs/PRD.md`/`docs/PRD_V2.md` for the
complete story list.

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
variables: `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN`. The real Turso
database is set up and is what the live deployment above actually uses.

So that the app is also runnable purely locally (and by QA) without needing
those credentials, `app/db.py` falls back to a **local libSQL/SQLite file**
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

## PIN recovery email: local fallback vs. Resend

`docs/DESIGN_V2.md` Section 1.5 specifies **Resend** for sending PIN-reset
emails, configured via `RESEND_API_KEY` (and `PUBLIC_BASE_URL`, used to build
the reset link). Nobody has set up a Resend account/verified sending domain
yet -- that's a real prerequisite that happens later, out-of-band.

Same pattern as the Turso fallback above: `app/email.py`'s
`send_pin_reset_email()` checks `RESEND_API_KEY` at send time:

- **Not set** (the default for local dev): the reset link is logged to the
  server console/logs instead of actually being emailed -- copy it from the
  terminal to test the "Forgot your PIN?" flow end to end with no external
  account.
- **Set**: the app calls the real Resend API instead.

To send real emails once Resend is set up:

```bash
export RESEND_API_KEY="re_..."
export PUBLIC_BASE_URL="https://<your-deployed-host>"
.venv/bin/uvicorn app.main:app --reload
```
