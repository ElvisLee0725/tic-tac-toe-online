# Technical Design Document: Tic Tac Toe Online

**Status:** For Developer implementation
**Owner:** Architect
**Source of truth for requirements:** `docs/PRD.md` (this document does not restate rationale already covered there; it makes the implementation decisions the PRD deliberately left open)
**Last updated:** 2026-08-02 (revised: database moved off Render's local disk to a decoupled managed store — see Sections 1, 3, 8, 9)

---

## 1. System Overview

A single small Python web app: one FastAPI process serving both the UI (server-rendered HTML) and a JSON API consumed by a small amount of vanilla JS for in-game interactivity, talking to a managed SQLite-compatible database (**Turso**, Section 3/9) over the network rather than a local file. No separate frontend service, no build pipeline, no other external services (auth provider, cache, queue). This matches the "hobbyist, not a studio" scope explicitly called out in scope.

The database is **deliberately decoupled from the web app's own filesystem/host** — this is a direct response to a stakeholder decision (Section 9): Render's free web-service disk is not durable across redeploys/idle spin-downs, so durable data must not live there at all, even though the app itself still runs on Render.

```
                 ┌──────────────────────────────────────────┐
                 │              Browser                      │
                 │  - Jinja2-rendered pages (nav, leaderboard,│
                 │    profile/stats, sign-in form)            │
                 │  - Vanilla JS "board.js" for the live game │
                 │    (fetch() calls to the JSON API below)   │
                 └───────────────┬────────────────────────────┘
                                 │ HTTPS
                                 ▼
                 ┌──────────────────────────────────────────┐
                 │      FastAPI app on Render (1 process)      │
                 │  ┌────────────┐  ┌────────────┐            │
                 │  │  page routes│  │  /api/* JSON│           │
                 │  │  (Jinja2)   │  │  routes     │           │
                 │  └─────┬──────┘  └──────┬──────┘           │
                 │        │                │                   │
                 │  ┌─────▼────────────────▼──────┐            │
                 │  │  game.py (rules/state)       │            │
                 │  │  ai.py (Easy/Medium/Hard)     │            │
                 │  │  auth.py (session cookies)    │            │
                 │  │  in-memory active_games dict  │            │
                 │  └─────────────┬────────────────┘            │
                 └────────────────┼─────────────────────────────┘
                                  │ libsql:// (network, TLS,
                                  │ auth token — NOT the local disk)
                                  ▼
                    ┌────────────────────────────┐
                    │   Turso (managed libSQL)     │
                    │   — separate free service,    │
                    │     independent of Render's    │
                    │     web-service filesystem      │
                    │   (profiles, sessions,           │
                    │    game_results)                  │
                    └────────────────────────────┘
```

Two kinds of server-side state, deliberately kept separate:
- **In-progress game state** (the live board while a game is being played) lives **in server memory**, keyed by a random `game_id`. Per FR-34, this is explicitly allowed to be lost on reload/restart, so a database table for it would be pure overhead. This is the one piece of state that's fine to lose if Render restarts the app.
- **Durable state** (profiles, sessions, completed-game history) lives in **Turso**, a managed database, specifically so it survives Render redeploys/restarts/idle spin-downs untouched — those events no longer touch durable data at all, since it was never on Render's disk to begin with.

This implies a hard constraint carried into deployment (Section 8): **the app must run as a single process/worker**. In-memory game state breaks under multiple workers/instances regardless of where the database lives. At hobby traffic levels this is a non-issue, not a compromise.

---

## 2. Frontend Approach — Decision: Server-rendered (FastAPI + Jinja2) + vanilla JS, no build step

**Chosen:** FastAPI serves Jinja2 templates for all "page" navigation (home/mode-select, sign-in, profile/stats, leaderboard). The one genuinely interactive piece — the live game board — is a small vanilla JS module (`static/js/board.js`) that talks to the JSON API (Section 4) with `fetch()` and updates the DOM directly, without a page reload.

**Rejected: separate static frontend (SPA) calling a pure JSON API.** Would require either a build step (bundler, npm) or hand-rolled client-side routing for what is functionally four pages. For a solo hobbyist developer this is pure overhead with no payoff — there's no team split between frontend/backend, no need for offline/mobile-app reuse of the API, and no complex client state to justify a framework.

**Why the hybrid still works cleanly:** the JSON API isn't a compromise bolted on for the SPA-that-wasn't — it's needed regardless, because AI moves and win/tie detection must be server-authoritative (Section 4). So the game board was always going to be a JS component calling an API; the only real decision was *everything else*, and for four mostly-static pages server-rendered HTML is simply less code, less JS, and easier to debug than a client router.

**Concretely:**
- `Jinja2Templates` + FastAPI's `StaticFiles` mount serve everything — no separate static host needed.
- One shared base template with a nav bar that reflects sign-in state (rendered server-side by reading the session cookie on each page request — see Section 6).
- Plain CSS (one stylesheet, no preprocessor). No JS framework, no npm, no `package.json` — `board.js` and a couple of small helper scripts are hand-written, loaded via `<script src>`.

---

## 3. Database Schema (SQLite dialect, hosted on Turso)

### Design decision: managed database, decoupled from the app host (Turso), not a local SQLite file

**Chosen:** the database engine stays **SQLite** (the schema/SQL below is unchanged, plain SQLite syntax) but the file itself is hosted by **Turso**, a managed libSQL (SQLite-compatible) service, reached over the network from the FastAPI app rather than opened as a local file. See Section 9 for the full hosting decision and tradeoffs; the point that matters for this section is that the schema below did not need to change to get real persistence — only the connection layer did (Section 8).

**Rejected: rewriting to Postgres** (e.g. Neon/Supabase's free tiers, also evaluated). Both offer genuinely free, persistent, no-card managed Postgres, but moving off SQLite would mean rewriting every `CREATE TABLE`/query in this section to Postgres syntax (`SERIAL` instead of `AUTOINCREMENT`, a different timestamp-default idiom instead of `strftime`, `ON CONFLICT` semantics, etc.) and swapping the whole data-access layer to an async Postgres driver — a materially larger change for a project this size, for no benefit the app actually needs. Turso gets the same durability guarantee with effectively no schema/query rewrite.

### Design decision: running counters on `profiles`, not aggregation from a game log

**Chosen:** `profiles.wins` / `profiles.losses` / `profiles.ties` are integer counters, incremented in the same transaction that finalizes a game. The leaderboard query reads directly off these columns.

**Rejected:** computing wins/losses/ties by `COUNT(*) ... GROUP BY` over a full per-game log at read time. Rejected because:
- The leaderboard (FR-28) and stats page (FR-25) are read far more often than games complete — aggregating on every read is wasted work for no benefit at this scale.
- Counters make the leaderboard query trivial (`ORDER BY` over already-materialized columns, Section 3.3) instead of a `JOIN`/`GROUP BY` over an unbounded table.
- A completed-game log is still kept (`game_results`, below) as an **audit trail**, not as the stats source of truth. It exists so a completed game's outcome is always traceable to something the server actually computed, and to leave room for a v2 "stats by mode/difficulty" feature without a schema migration on `profiles`. It is intentionally not queried on any hot path.

### Schema

```sql
-- One row per player identity (Section 4/6 cover how profiles are created/verified).
CREATE TABLE profiles (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name  TEXT NOT NULL COLLATE NOCASE UNIQUE,  -- enforces FR-15 case-insensitive uniqueness
    pin_hash      TEXT NOT NULL,                         -- salted hash, never the raw PIN (see note below)
    pin_salt      TEXT NOT NULL,
    wins          INTEGER NOT NULL DEFAULT 0,
    losses        INTEGER NOT NULL DEFAULT 0,
    ties          INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
-- display_name's UNIQUE ... COLLATE NOCASE constraint is also the lookup index used at sign-in.

-- Auto-recognition token (Section 6). One row per signed-in browser.
CREATE TABLE sessions (
    token         TEXT PRIMARY KEY,                      -- opaque random token, stored in an HTTP-only cookie
    profile_id    INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- Append-only audit log of completed games. NOT used by the leaderboard/stats hot paths.
-- Guest "vs AI" games (FR-17) are never written here — they never touch the DB at all.
CREATE TABLE game_results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    mode          TEXT NOT NULL CHECK (mode IN ('ai','human')),
    difficulty    TEXT CHECK (difficulty IN ('easy','medium','hard')),  -- NULL when mode='human'
    x_profile_id  INTEGER NOT NULL REFERENCES profiles(id),
    o_profile_id  INTEGER REFERENCES profiles(id),        -- NULL when opponent was the AI
    result        TEXT NOT NULL CHECK (result IN ('x_won','o_won','tie')),
    played_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX idx_game_results_x ON game_results(x_profile_id);
CREATE INDEX idx_game_results_o ON game_results(o_profile_id);
```

**PIN storage note:** the PRD explicitly says this is not a real auth system and doesn't need cryptographic hardening — but hashing the PIN costs nothing extra to implement (one `hashlib.sha256(salt + pin)` call) and means a copy of the `.db` file doesn't hand over every PIN in plaintext. Firm decision: store a per-profile random salt (`secrets.token_hex(8)`) and `sha256(salt + pin)`. This is proportionate hygiene, not an attempt at bank-grade security.

### 3.3 Leaderboard query (FR-28–FR-33, PRD Q1)

Ranking = `wins - losses`, minimum 5 completed games (`wins + losses + ties >= 5`), tie-break by higher `wins`, then earlier `created_at` — exactly the PRD's recommended default, adopted as-is.

```sql
-- Top 10 (FR-28, FR-30, FR-31)
SELECT id, display_name, wins, losses, ties, (wins - losses) AS score, created_at
FROM profiles
WHERE (wins + losses + ties) >= 5
ORDER BY score DESC, wins DESC, created_at ASC
LIMIT 10;
```

```sql
-- Signed-in player's own rank, for "you're #N" when outside the top 10 (FR-33)
-- :score / :wins / :created_at are the signed-in profile's own values.
SELECT COUNT(*) + 1 AS my_rank
FROM profiles
WHERE (wins + losses + ties) >= 5
  AND (
        (wins - losses) > :score
     OR ((wins - losses) = :score AND wins > :wins)
     OR ((wins - losses) = :score AND wins = :wins AND created_at < :created_at)
      );
```

Both queries are full-table scans over `profiles`, which is fine — at hobby-project scale (hundreds to low thousands of profiles) SQLite does this in sub-millisecond time with no index. If the site ever gets large enough to matter, add a partial index (`CREATE INDEX ... ON profiles(...) WHERE wins+losses+ties >= 5`) — not needed now, not built now.

---

## 4. API Design

**Authoritative-server principle (this is the anti-cheat design for this project):** there is **no endpoint that accepts a client-declared game result.** A client can never call something like `POST /results {winner: "me"}`. The only way `profiles.wins/losses/ties` or `game_results` changes is as a side effect of the server itself resolving a game to a terminal state inside `POST /api/games/{id}/moves`, using board state the server has been tracking move-by-move. Likewise, AI moves are computed and applied **server-side**, inside that same endpoint — the client only ever sends the human's chosen cell, never an AI move, so Hard's "never loses" guarantee can't be bypassed by a modified client.

Remaining attack surface, and how it's handled (kept deliberately lightweight — the PRD explicitly puts rate-limiting/anti-cheat hardening out of scope):
- **Guessing/hijacking someone else's `game_id`:** IDs are random UUIDv4s (~122 bits), not sequential — unguessable in practice. Worst case if guessed: someone pokes a move into a casual, no-stakes local game. Accepted risk, no further mitigation built.
- **Move validity:** every move is server-checked against the in-memory board (cell in range, cell empty, game still `in_progress`, correct player's turn) before being applied — this is just FR-5 enforcement, and it also happens to close off "submit an illegal move to corrupt state."
- **PIN brute force** (10,000 possible 4-digit PINs): no rate limiting is implemented, matching the PRD's explicit scope call. Flagged again as an optional future add in Section 9.

### 4.1 Session / Profile endpoints (FR-18–FR-24)

| Method & Path | Request body | Response | Notes |
|---|---|---|---|
| `POST /api/session` | `{ "display_name": str, "pin": str }` | `200 { profile: {id, display_name, wins, losses, ties, created_at} }` and sets `session_token` cookie | Combined create-or-signin (FR-18/19). New name → creates profile. Existing name + correct PIN → signs in. Existing name + wrong PIN → `401 { error: "wrong_pin" }` (FR-20), no row modified. Malformed name/PIN (Section "Identity format", carried over from PRD Q4) → `422` before touching the DB (FR-21). |
| `GET /api/session` | — (reads cookie) | `200 { profile: {...} }` or `401 { error: "not_signed_in" }` | Auto-recognition (FR-22/35) and "my stats" (FR-25) in one call — the profile object already includes wins/losses/ties, so no separate `/me` endpoint is needed. |
| `DELETE /api/session` | — | `204`, clears cookie | Sign out / switch profile (FR-23). Deletes the `sessions` row so the old token can't be replayed. |

### 4.2 Game endpoints

| Method & Path | Request body | Response |
|---|---|---|
| `POST /api/games` | `{ "mode": "ai" \| "human", "difficulty"?: "easy"\|"medium"\|"hard", "guest"?: bool, "opponent_name"?: str, "opponent_pin"?: str }` | `201 { game_id, mode, difficulty, board, current_turn: "X", status: "in_progress", x: {display_name}, o: {display_name} }` |
| `POST /api/games/{game_id}/moves` | `{ "cell": 0-8 }` | `200 { game_id, board, current_turn, status, winner: "X"\|"O"\|null, ai_move: {cell:int}\|null, profile_updates?: {...} }` |
| `GET /api/games/{game_id}` | — | `200` same shape as above (state resync only; optional, see Section 9) |

`POST /api/games` rules, firmly resolved (PRD left mode setup mechanics unspecified):
- **Human always plays X and moves first** (FR-1); in `vs AI` the AI is always O; in `vs Human (local)` the browser's signed-in profile (from the session cookie) is X, and the second local player is O.
- `mode: "ai", guest: true` — no cookie required (FR-17). Server creates an in-memory session with `x_profile_id = null`; on completion nothing is written to the DB.
- `mode: "ai", guest: false` — requires a valid session cookie (else `401`); `x` = signed-in profile, `o` = AI (`o_profile_id = null` in the eventual `game_results` row).
- `mode: "human"` — requires a valid session cookie for X **and** `opponent_name`/`opponent_pin` in the body for O, checked with the same verification used by `POST /api/session` (FR-19/20 logic, reused — but this does **not** switch the browser's own cookie/session, since the device owner stays signed in as X). Wrong PIN → `401 { error: "opponent_signin_failed" }`, no game created. This is how FR-10 ("both participants must be signed in") is satisfied without a second device.

`POST /api/games/{game_id}/moves` flow (this is where AI turns are handled — no separate "get AI move" endpoint exists):
1. Look up the game in the in-memory `active_games` dict; `404` if unknown/expired, `409` if already finished.
2. Validate the move (cell empty, in range) against `current_turn`; apply it.
3. Check win/tie (Section 5 covers detection). If terminal → finalize (step 5) and return; `ai_move` is `null`.
4. Else, if `mode == "ai"`: compute the AI's reply via `ai.py` for the game's difficulty, apply it immediately, check win/tie again. The response always reflects the state *after* the AI's reply too, so the client renders both moves from one round trip — this is how FR-14's "feels immediate" is met (one HTTP round trip, no polling).
5. **Finalize on terminal state:** in one DB transaction, insert a `game_results` row (skipped entirely if `x_profile_id` is null, i.e. a guest game) and increment `wins`/`losses`/`ties` on the participating profile(s) per PRD Q8 (loser gets a loss, winner a win, both get a tie on a draw; the AI itself never gets a row since it has no profile). Response includes `profile_updates` so the client can show "Stats updated" without a second fetch. Remove the game from `active_games`.

### 4.3 Leaderboard endpoint (FR-28–FR-33)

| Method & Path | Response |
|---|---|
| `GET /api/leaderboard` | `200 { top: [{rank, display_name, wins, losses, ties, score}], me: {rank, display_name, wins, losses, ties, score} \| null }` |

No auth required to call it (FR-28 is public). If the request carries a valid session cookie, the server also computes `me` using the query in Section 3.3 — but only populates it when the signed-in profile **qualifies** (≥5 games) **and** is outside the top 10; otherwise `me` is `null` (they can already see themselves in `top`, or they don't have a ranked score yet). This is the FR-33 "your rank" feature, and confirms Q6's concern: it's one cheap extra query, no material complexity added.

---

## 5. Game Rules Engine (`game.py`)

Board representation: a 9-character string or list, index 0–8 mapped left-to-right, top-to-bottom (`0 1 2 / 3 4 5 / 6 7 8`), `'_'` for empty.

Win check: a fixed list of the 8 winning lines, checked after every move:

```python
LINES = [
    (0,1,2), (3,4,5), (6,7,8),   # rows
    (0,3,6), (1,4,7), (2,5,8),   # columns
    (0,4,8), (2,4,6),            # diagonals
]
```
A move is a win if any line in `LINES` is fully occupied by the mover's symbol. A tie is: no win, and no `'_'` left on the board. This single function is used everywhere a result is needed (move endpoint, and by the AI's minimax to score terminal states) — one implementation, no duplicated logic between "real" win detection and AI lookahead.

---

## 6. AI Implementation (`ai.py`)

All three tiers take `(board, ai_mark)` and return a single cell index. All AI computation happens server-side inside the move endpoint (Section 4.2) — this is what makes Hard's "never loses" guarantee actually hold, since a tampered client has no way to see or influence the AI's chosen move before it's applied.

- **Easy (FR-11):** uniform-random choice among currently-empty cells. No win/block checking at all — deliberately "dumb," matching the PRD's "no deliberate blocking or winning strategy." Nothing more sophisticated needed or wanted here.
- **Medium (FR-12, PRD Q3):** fixed 3-step heuristic, in order:
  1. If any empty cell completes a line for the AI, take it (immediate win).
  2. Else if any empty cell completes a line for the opponent, take it (immediate block).
  3. Else pick randomly among remaining empty cells, weighted center > corners > edges (weights e.g. center=3, corners=2, edges=1, using `random.choices`) so Medium's fallback play looks slightly more natural than pure-random without adding any lookahead. This is intentionally *not* minimax-with-depth-cap, per the PRD's explicit reasoning (avoids accidentally becoming unbeatable).
- **Hard (FR-13, PRD Q2):** full minimax over the remaining game tree, depth-scored so it prefers a faster win / slower loss (`score = 10 - depth` for an AI win, `depth - 10` for an AI loss, `0` for a tie). On a 3×3 board the full tree from an empty board is ~255K leaf nodes worst case, and far smaller once a real game is partway through — this runs in low single-digit milliseconds in pure Python, comfortably inside FR-14's 1-second budget with no optimization. **Alpha-beta pruning is optional and not required** — noted per PRD Q2, skip it unless it's convenient; do not spend implementation time on it.

```
minimax(board, mark_to_move, ai_mark):
    if terminal(board): return score(board, ai_mark), None
    best = -inf if mark_to_move == ai_mark else +inf
    for each empty cell:
        place mark_to_move there
        value, _ = minimax(board, other_mark, ai_mark)
        undo
        best = max/min(best, value) accordingly, tracking the cell that produced it
    return best, best_cell
```

---

## 7. Identity / Recognition Mechanism (FR-22, FR-35, FR-36)

**Chosen: HTTP-only session cookie, opaque random token, server-side `sessions` table.**

Flow: `POST /api/session` on success generates `token = secrets.token_urlsafe(32)`, inserts `(token, profile_id)` into `sessions`, and responds with `Set-Cookie: session_token=<token>; HttpOnly; SameSite=Lax; Secure; Max-Age=31536000; Path=/`. Every subsequent request (page loads and `/api/*` calls) reads that cookie, looks up `sessions.profile_id`, and treats the request as "signed in as that profile" if found — this is FR-22/FR-35's auto-recognition, requiring zero client-side JS logic since the browser sends the cookie automatically. `DELETE /api/session` (sign out, FR-23) deletes the `sessions` row and clears the cookie via `Max-Age=0`. If the cookie is missing, unrecognized, or its row was deleted, the server responds `401` from `GET /api/session` and the frontend shows the name+PIN form (FR-36), which on success re-establishes recognition.

**Rejected: token in `localStorage` sent as a manual header.** Would require every page (not just the JS-driven game board) to run client-side JS before it can render sign-in state correctly, undermining the server-rendered-pages decision in Section 2 — the nav bar would flash "not signed in" before JS runs. A cookie is read server-side on the very first response, so pages render correctly signed-in on first paint.

Explicitly **not** hardened beyond this, matching the PRD's framing that this is a casual-game identity mechanism, not real auth: the token is a long random string (unguessable in practice) but there's no expiry sliding-window logic, no device fingerprinting, no CSRF token. `SameSite=Lax` is included because it's a zero-cost default in most web frameworks and blocks the most trivial cross-site abuse, but a from-scratch CSRF-token scheme was considered and rejected as disproportionate — worst case of a CSRF here is someone tricks a signed-in player into starting an unwanted game or signing out, which is low-stakes for a casual game with no real money/PII involved.

---

## 8. Project Structure

```
tic-tac-toe-online/
├── app/
│   ├── main.py            # FastAPI app instance, route registration, startup (opens/initializes DB)
│   ├── db.py               # libsql connection helper (Turso) + CREATE TABLE statements (Section 3)
│   ├── auth.py              # session cookie issuing/reading, sign-in/create-profile logic, PIN hashing
│   ├── game.py              # board rules: win/tie detection, move validation (Section 5)
│   ├── ai.py                # easy/medium/hard move selection, minimax (Section 6)
│   ├── games_api.py         # POST /api/games, POST /api/games/{id}/moves, GET /api/games/{id}
│   ├── profiles_api.py      # POST/GET/DELETE /api/session
│   ├── leaderboard_api.py   # GET /api/leaderboard (Section 3.3 queries)
│   ├── pages.py             # Jinja2 page routes (home, sign-in, game, profile, leaderboard)
│   ├── templates/
│   │   ├── base.html         # shared layout, nav bar (reads session cookie via a dependency)
│   │   ├── index.html         # mode/difficulty picker
│   │   ├── game.html           # board container; board.js does the rest
│   │   ├── signin.html          # name+PIN form
│   │   ├── profile.html          # own stats (FR-25)
│   │   └── leaderboard.html       # top 10 + "your rank"
│   └── static/
│       ├── css/app.css
│       └── js/
│           ├── board.js       # fetch()-driven game board (POST /api/games, .../moves)
│           └── signin.js       # small helper for the sign-in form
├── requirements.txt          # fastapi, uvicorn, jinja2, python-multipart, libsql-client (Turso driver)
└── docs/
    ├── PRD.md
    └── DESIGN.md
```

No `.db` file lives in the repo or on the deployed app's filesystem at all — `db.py` connects to Turso using two environment variables, `TURSO_DATABASE_URL` (a `libsql://...turso.io` URL) and `TURSO_AUTH_TOKEN`, both set as secrets on the host (Section 9), never committed. The `libsql-client`/`libsql` package's connection object exposes essentially the same `execute()`/`cursor()`/`commit()` shape as stdlib `sqlite3`, so `db.py` is a thin, easily-swappable adapter — this is what keeps the migration path in Section 9 open (swap the two env vars, or later the driver, without touching `game.py`, `ai.py`, or any of the `*_api.py` route files, which only ever call through `db.py`).

---

## 9. Deployment Plan

**Chosen: Render (free Web Service tier) for the app, + Turso (free managed libSQL database) for all durable data, kept fully separate.**

This is a revision of the original plan. The original version put the SQLite file on Render's own web-service disk and flagged that as a real risk (Render's free tier has no persistent disk — the filesystem doesn't reliably survive redeploys/restarts/idle spin-downs). The stakeholder's call: eliminate that risk rather than accept it, while staying fully free. The fix is architectural, not a Render setting — **move durable data off the app host's disk entirely**, onto a database that persists independently of Render. The app hosting decision itself is unchanged.

**App hosting — Render free Web Service, same reasoning as before:** no credit card required, free indefinitely, deploys directly from GitHub, first-class support for `uvicorn app.main:app --host 0.0.0.0 --port $PORT` with zero extra config, free HTTPS on `https://<name>.onrender.com`. Render's disk is still ephemeral, but that no longer matters — nothing durable is stored there anymore (Section 1).

**Database hosting — Turso free tier, chosen over the alternatives evaluated:**

| Option | Verdict | Why |
|---|---|---|
| **Turso (libSQL)** | **Chosen** | Free tier: 5GB storage, 100 databases, no credit card, does not expire. Database hibernates after an hour of idle and **auto-wakes on the next connection** — no manual step, no risk of the site appearing "down" after being quiet for a while. SQLite-compatible, so the schema in Section 3 needed no rewrite — only the connection layer (Section 8) changes. |
| Neon (Postgres) | Rejected | Also a genuinely free, permanent, no-card tier (0.5GB storage, 100 compute-hours/month, auto-suspends after 5 min idle and auto-resumes on next query — a fine option on its own merits). Rejected only because it's Postgres: would force a schema/query rewrite and a driver swap for no durability benefit over Turso. |
| Supabase (Postgres) | Rejected | Free tier pauses the entire project after **7 days of inactivity**, and resuming requires a **manual click in the Supabase dashboard** — a real risk for a low-traffic hobby site that could go quiet for a week and then stay "down" until someone notices and manually restores it. Same Postgres-rewrite cost as Neon on top of that. |
| Render's own free PostgreSQL | Rejected | Free Render databases **expire 30 days after creation** and are deleted after a 14-day grace period unless upgraded to paid — doesn't meet "persist independently, stay free" at all; it would just move the same expiry problem from disk to database. |

**Deployment mechanics:**
- Create a Turso database (via the Turso CLI or dashboard — no card needed) and generate an auth token. Set `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` as Render environment variables (secrets, not committed to the repo).
- `requirements.txt` + a `render.yaml` (or just the dashboard's "Python" preset) with start command `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- **Single instance, single worker** — required (Section 1) because active game state is in-process memory. (This is no longer also required for SQLite-writer-concurrency reasons — Turso's libSQL supports multiple writers — but the in-memory `active_games` dict still pins the app to one process regardless.) Do not enable Render's autoscaling or multiple instances for this service.
- Auto-deploy on push to `main`.
- Two independent, expected "cold start" delays, both accepted as normal free-tier UX and not bugs to fix: Render's own idle spin-down (first request after inactivity takes a few seconds to wake the app), and Turso's separate hourly hibernation (adds a small delay to the *first query* after an hour idle, then it's warm again). Neither loses data; both just add latency to the first request/query after a quiet period.

**Migration path, kept explicitly open (per the stakeholder's ask not to design into a corner):**
- **Upgrading Render to a paid instance later:** nothing about the database changes. Turso is already fully decoupled from Render's disk, so a Render plan upgrade is purely about compute/uptime characteristics, not storage — no data migration needed either way.
- **Outgrowing Turso's free tier (past 5GB, or wanting Turso's paid SLA/backup features):** upgrade the same Turso project to a paid plan; the connection URL/token pattern is unchanged, so it's a billing change, not a code or schema change.
- **Leaving Turso entirely for a different engine (e.g. Postgres, if the project ever needs Postgres-only features):** this is the one path that does cost a rewrite — the SQL in Section 3 is plain SQLite dialect, and `db.py` is the single, intentionally-thin adapter every route goes through (Section 8), so the blast radius is contained to that one file plus the `CREATE TABLE` statements, not spread across the app.

---

## 10. Open Items for the Developer

Same pattern as the PRD: each has a firm default so implementation isn't blocked, flagged where it's a genuine "revisit later" rather than a decision.

| # | Item | Default | Notes |
|---|---|---|---|
| D1 | `GET /api/games/{game_id}` resync endpoint | Implement it (it's cheap — same code path as the move response, no new logic) | Not required by any FR (FR-34 explicitly allows losing in-progress state on reload), but it's low-cost and makes the game board resilient to e.g. a mobile browser backgrounding mid-game. Skip if time-pressured — genuinely optional. |
| D2 | Sign-in rate limiting (PIN brute force) | Not built | Matches the PRD's explicit "anti-cheat/rate-limiting beyond basic validation is out of scope" (Section 4 of the PRD). If ever revisited, a simple in-memory per-IP attempt counter in `auth.py` would be a proportionate add — no need for anything more.  |
| D3 | Multi-instance/horizontal scaling | Not supported; single process only | Flagged as an architectural constraint (Section 1, Section 9), not a TODO — revisit only if real traffic ever demands it, which would also require moving `active_games` out of process memory (e.g., into SQLite or a small cache) and reconsidering SQLite itself. Out of scope for v1. |
| D4 | Data durability | Resolved — Turso (managed libSQL), fully decoupled from Render's disk (Section 9) | No longer an open risk; kept here only to record that it was actively addressed, not overlooked. Watch the 5GB/free-tier ceiling as a much later concern — not relevant at hobby scale. |
| D6 | Turso's Python driver choice (`libsql-client` vs `libsql`) | Developer's call at implementation time | Both wrap a sqlite3-like DB-API around the same Turso connection; pick whichever has the more current docs/examples when implementation starts (Turso's SDK has iterated a few times). Not a design-level decision — `db.py` isolates this choice from the rest of the app (Section 8). |
| D5 | CSS/JS approach for pages beyond the board | Plain hand-written CSS/JS, no framework | Consistent with Section 2's no-build-step decision. Not worth a second look unless the UI scope grows significantly beyond what's in the PRD. |

---
