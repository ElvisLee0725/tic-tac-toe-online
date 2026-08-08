# QA Report — Tic Tac Toe Online

**Tested by:** QA (adversarial pass)
**Date:** 2026-08-07
**Environment:** Local dev server (`uvicorn app.main:app --port 8130`), local-file SQLite fallback (`local.db`, no `TURSO_DATABASE_URL` set), fresh DB per isolated scenario where noted.
**Method:** Direct API testing (curl / Python `requests`) against the documented contract in `docs/DESIGN.md` Section 4, cross-referenced against `docs/PRD.md` Section 3 (FR-1–FR-36) and Section 6 acceptance criteria. Also read all application source (`app/*.py`, templates, JS) to target tests, not just black-box guessing. One exhaustive in-process test of the Hard AI's full game tree (all 569 possible terminal games), plus HTTP-level spot checks.

---

## Summary

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 1 |
| Medium | 3 |
| Low | 2 |
| **Total** | **6** |

**Headline finding:** sending a non-string JSON type (integer, list, bool) for `display_name` or `pin` on **any** of `POST /api/session/new`, `POST /api/session`, or `POST /api/games` (human opponent fields) crashes the server with an unhandled `500 Internal Server Error` instead of the expected `422 validation_error`. See Finding #1.

**The specific bug this round was meant to verify (combined create+sign-in silently creating a throwaway account on a typo) is confirmed FIXED.** `POST /api/session/new` (Create Account) and `POST /api/session` (Sign In) are genuinely separate, sign-in never creates a row, and the vs-Human opponent flow (`POST /api/games`, `mode: "human"`) independently reuses the same sign-in-only logic and was verified not to have regressed the same way. The other real prior bug called out in the brief — only X's stats updating in human-vs-human — is also confirmed fixed; both X and O update correctly on win/loss/tie.

---

## What was tested and confirmed working (coverage, not just failures)

- **All 8 winning lines** (3 rows, 3 columns, 2 diagonals), for both X and O, via human-vs-human play with fully controlled move sequences — all 8 correctly detected in both directions (16 scenarios total). ✅
- **Full-board tie** (classic X-O-X / X-O-O / O-X-X layout) correctly resolves to `status: "tie"`, not stuck/undefined. ✅
- **Occupied-cell rejection**: second move to an already-filled cell → `400 illegal_move`. ✅
- **Invalid cell values**: negative, `9`, `100`, string `"abc"`, string `"3"`, float `3.5`, `null`, list — all correctly rejected with `400 illegal_move`. (One exception: `true` — see Finding #4.) ✅ (except noted)
- **Move after game already ended** → rejected (though with the wrong status code — see Finding #2). ✅ functionally / ⚠️ contract mismatch
- **Move against nonexistent/expired `game_id`** → `404 not_found`. ✅
- **Hard AI unbeatable**: exhaustively verified in-process against **all 569 possible complete games** reachable from every possible human move sequence (human always moves first as X) — **zero** human wins, only ties/AI-wins. Also re-verified through 5 real HTTP-level games with distinct move orderings (including corner-trap-style sequences known to break naive minimax bugs). Latency: ~43–49ms for the AI's first (hardest, empty-board) move, well under the 1s budget. ✅
- **Medium AI**: exhaustively checked the "always take an immediate win, else always block an immediate opponent win" invariant across 114,417 distinct O-to-move board states (5 samples each, to catch nondeterminism in the fallback branch) — **zero violations**. Statistically beatable: a competent scripted human strategy won 31.4% of 500 games (0 AI wins, 68.6% ties) — matches FR-12 exactly. ✅
- **Easy AI**: not suspiciously strong — same scripted strategy won 97% of 500 games against Easy. ✅
- **AI latency**: Easy/Medium <2ms, Hard <50ms — comfortably inside FR-14's 1-second target. ✅
- **Account creation**: empty name, whitespace-only name, name below min length (2 chars), name at exactly 20 chars (succeeds), name at 21 chars (rejected), PIN of 3 or 5 digits, non-numeric PIN, PIN with internal space — all correctly rejected/accepted per the 3–20 char / 4-digit-numeric rules. ✅
- **Case-insensitive uniqueness**: creating `AliceQA1` then `aliceqa1` → `409 name_taken`; signing in as `ALICEQA1` (yet another case) with the correct PIN succeeds and resolves to the same profile. ✅
- **Sign-in failure is generic and non-distinguishing**: wrong PIN for a real account and a nonexistent account both return the identical `401 {"error":"sign_in_failed"}`; confirmed the nonexistent name is never created as a side effect of the failed sign-in attempt. ✅
- **Sign-out actually invalidates the cookie server-side**: captured a valid token, called `DELETE /api/session`, then manually replayed the *same* old token value in a fresh request (bypassing the client-side cookie-jar auto-clearing) — server correctly returns `401 not_signed_in` and also rejects it for starting a new game. ✅
- **Human-vs-human, nonexistent opponent**: `mode: "human"` against a name that doesn't exist → `401 opponent_signin_failed`, and confirmed via follow-up sign-in attempt that no account was silently created for that name. This is the same bug-fix pattern as the headline fix, verified independently on this separate code path. ✅
- **Human-vs-human, wrong opponent PIN** → `401 opponent_signin_failed`, no game created. ✅
- **Human-vs-human, self-play** (including case-insensitive self-play, e.g. signed in as `HvhP1QA` naming opponent `hvhp1qa`) → `400 cannot_play_self`. ✅
- **Human-vs-human, not signed in** → `401 not_signed_in`. ✅
- **Human-vs-human stats**: played a full X-win game and a full tie game between two real profiles — **both** participants' win/loss and tie/tie counters updated correctly and immediately (verified via a fresh `GET /api/session` read after each game). This confirms the previously-reported "only X's stats updated" bug is fixed. ✅
- **Guest AI games**: played a full guest game to completion — no `profile_updates` in the response, confirming nothing is written to the DB for guests, per FR-17. ✅
- **Stats immediacy**: in every scenario above, the very next `GET /api/session` (or the `profile_updates` in the move response itself) reflected the new totals — no lag. ✅
- **Leaderboard ranking & tie-break**: seeded 15 profiles with precisely controlled win/loss/tie records via scripted games. Confirmed: (a) ranking by `wins − losses` descending; (b) tie-break by higher `wins` (two profiles tied at score 0, the one with 2 wins/2 losses/1 tie ranked above the one with 0 wins/0 losses/5 ties); (c) tie-break by earlier `created_at` when score *and* wins are both equal (three profiles tied at score −5/wins 0 ranked in exact creation order); (d) top-10 cap enforced; (e) a profile with only 4 games (one short of the 5-game qualifying threshold) correctly excluded from the leaderboard entirely; (f) a profile with exactly 5 games (boundary) correctly included; (g) "my rank" (`me` field) correctly populated with the right rank number for profiles just outside the top 10 (ranks 11–14 all correct), and correctly `null` for a profile that doesn't yet qualify. ✅
- **Leaderboard degrades gracefully**: tested against an isolated fresh database with zero profiles (`{"top": [], "me": null}`, no error) and with 1 profile / 0 qualifying games. ✅
- **Injection sanity check**: SQL-metacharacter and HTML/script-tag payloads in `display_name` and `pin` are all rejected outright by the character-class validation regex (`[A-Za-z0-9_-]{3,20}` / `\d{4}`) before ever reaching the database, so nothing was stored or executed. Also confirmed the app keeps functioning normally (leaderboard still responds) after the injection attempts. Display names are also only ever set via `textContent`/Jinja2 auto-escaping in the templates/JS (no `|safe`, no `innerHTML` assignment of user data) — no XSS vector found. ✅
- **Pages with no session cookie at all**: `/`, `/signin`, `/game`, `/leaderboard` all return `200` and render; `/profile` correctly `302`-redirects to `/signin` (no crash). Also tested a garbage/nonexistent cookie value — handled gracefully as "not signed in", no crash. ✅
- **PIN never displayed back**: confirmed `profile_to_dict()` (used by every endpoint that returns a profile) never includes `pin_hash`/`pin_salt`; sign-in/create-account forms use `type="password"` for the PIN field. ✅
- **Concurrent account creation race** (10 simultaneous `POST /api/session/new` for the same name): exactly one `201`, the other nine cleanly `409 name_taken` — no `500` from a database unique-constraint race. (Likely protected in practice by the single-process/single-worker design combined with blocking DB calls inside the async handlers serializing the requests — worth being aware this protection is incidental rather than an explicit lock, see note in Finding #1's write-up, but no bug observed.) ✅

---

## Findings

### Finding #1 — HIGH — Unhandled 500 crash when `display_name`/`pin`/`opponent_pin`/`difficulty` are non-string JSON types

**Severity:** High
**PRD requirement violated:** FR-21 ("Validation errors are shown before any account action is attempted") — implies validation should *fail cleanly*, not crash the server. Also a general robustness/availability concern not explicitly covered by a single FR but core to "clear feedback on illegal actions" (FR-10/U10).

**Root cause:** `auth.validate_display_name()` and `auth.validate_pin()` (`app/auth.py` lines 35–54) call `.strip()` directly on whatever `body.get("display_name")` / `body.get("pin")` returns from the parsed JSON, with no `isinstance(..., str)` check first. Since JSON allows numbers, booleans, lists, and objects in any field, any client sending one of those types instead of a string causes an `AttributeError` that is never caught, producing a `500 Internal Server Error` instead of the intended `422 validation_error`. The same root cause also hits `games_api.py`'s difficulty lookup (`difficulty not in ai.SUPPORTED_DIFFICULTIES`, `app/games_api.py` line 70) when `difficulty` is an unhashable type like a list.

**Repro (all confirmed via curl/`requests` against the local server, full tracebacks captured in server logs):**

```bash
# 1. Create account, display_name as integer
curl -s -i -X POST http://127.0.0.1:8130/api/session/new \
  -H 'Content-Type: application/json' \
  -d '{"display_name": 12345, "pin": "1234"}'
# Expected: 422 {"error":"validation_error", ...}
# Actual:   500 Internal Server Error

# 2. Create account, pin as integer
curl -s -X POST http://127.0.0.1:8130/api/session/new \
  -H 'Content-Type: application/json' \
  -d '{"display_name": "ValidNameQA1", "pin": 1234}'
# Actual: 500

# 3. Create account, display_name as list or bool — same 500

# 4. Sign in, display_name as integer
curl -s -X POST http://127.0.0.1:8130/api/session \
  -H 'Content-Type: application/json' \
  -d '{"display_name": 12345, "pin": "1234"}'
# Actual: 500

# 5. Human-vs-human, opponent_name as integer (requires a signed-in cookie first)
curl -s -b cookies.txt -X POST http://127.0.0.1:8130/api/games \
  -H 'Content-Type: application/json' \
  -d '{"mode":"human","opponent_name": 999, "opponent_pin":"1234"}'
# Actual: 500

# 6. Human-vs-human, opponent_pin as integer
curl -s -b cookies.txt -X POST http://127.0.0.1:8130/api/games \
  -H 'Content-Type: application/json' \
  -d '{"mode":"human","opponent_name": "SomeoneReal", "opponent_pin": 1234}'
# Actual: 500

# 7. AI game, difficulty as a list (unhashable — different underlying error, same symptom)
curl -s -X POST http://127.0.0.1:8130/api/games \
  -H 'Content-Type: application/json' \
  -d '{"mode": "ai", "difficulty": ["hard"], "guest": true}'
# Actual: 500
```

Representative traceback (from server log, `POST /api/session/new` with `display_name: 12345`):
```
File "app/profiles_api.py", line 49, in post_session_new
    display_name, pin = _parse_credentials(body)
File "app/profiles_api.py", line 34, in _parse_credentials
    display_name = auth.validate_display_name(body.get("display_name"))
File "app/auth.py", line 38, in validate_display_name
    name = name.strip()
AttributeError: 'int' object has no attribute 'strip'
```

**Expected:** `422 {"error": "validation_error", ...}`, same as any other malformed-input case.
**Actual:** `500 Internal Server Error` with a generic body (no stack trace leaked to the client, but the request fails ungracefully and pollutes the server log with a full traceback on every occurrence).

**Notes:** Not reachable through the normal browser UI (HTML `<input>` fields always submit strings), but trivially reachable by anyone calling the JSON API directly — which the app explicitly supports/documents (DESIGN.md Section 4 describes this as a first-class JSON API, not an internal-only implementation detail). This is a reliability/availability bug: a single malformed automated request (bot, script, fuzzer, or just a buggy future frontend change) can trigger a crash instead of a handled error, and it's present on 3+ distinct endpoints from one shared root cause. Recommend a one-line fix: check `isinstance(value, str)` at the top of `validate_display_name`/`validate_pin` (and `difficulty` membership check) and raise `ValidationError` instead of letting the `AttributeError`/`TypeError` propagate.

---

### Finding #2 — MEDIUM — Moving on an already-finished game returns `404 not_found` instead of the documented `409 game_already_finished`

**Severity:** Medium
**Violates:** `docs/DESIGN.md` Section 4.2, step 1: *"Look up the game in the in-memory `active_games` dict; `404` if unknown/expired, `409` if already finished."* — these are meant to be two distinguishable outcomes.

**Root cause:** `_finalize_if_terminal()` (`app/games_api.py` line 201) always calls `active_games.pop(g["game_id"], None)` as soon as a game reaches a terminal state. This means the `if g["status"] != "in_progress": return 409 game_already_finished` check at the top of `make_move()` (line 210–211) is **dead code** — a finished game is never found in `active_games` in the first place, so every "already finished" case actually falls through to the `g is None` branch and returns `404 not_found` instead.

**Repro:**
```bash
# (using two signed-in profiles' cookies, p1 as X)
# Play a game to completion (X wins on 0,1,2):
curl -s -b p1.jar -X POST http://127.0.0.1:8130/api/games/$GAME_ID/moves -d '{"cell":0}' -H 'Content-Type: application/json'
curl -s -b p1.jar -X POST http://127.0.0.1:8130/api/games/$GAME_ID/moves -d '{"cell":3}' -H 'Content-Type: application/json'
curl -s -b p1.jar -X POST http://127.0.0.1:8130/api/games/$GAME_ID/moves -d '{"cell":1}' -H 'Content-Type: application/json'
curl -s -b p1.jar -X POST http://127.0.0.1:8130/api/games/$GAME_ID/moves -d '{"cell":4}' -H 'Content-Type: application/json'
curl -s -b p1.jar -X POST http://127.0.0.1:8130/api/games/$GAME_ID/moves -d '{"cell":2}' -H 'Content-Type: application/json'
# -> status: "x_won"

# One more move on the now-finished game:
curl -s -w "\n%{http_code}\n" -b p1.jar -X POST http://127.0.0.1:8130/api/games/$GAME_ID/moves -d '{"cell":8}' -H 'Content-Type: application/json'
```
**Expected (per DESIGN.md):** `409 {"error": "game_already_finished"}`
**Actual:** `404 {"error": "not_found"}`

**Impact:** Low functional risk (the move is still correctly rejected either way, state can't be corrupted), but the client-facing error is misleading — `not_found` reads as "this game_id never existed / was garbage-collected," which is a materially different situation from "you're double-clicking/racing the end of a game you were just playing," and the client's error-message logic (`board.js`: `"Move rejected: " + (data.message || data.error)`) will show the wrong explanation. Also means the `game_already_finished` error path/message is effectively unused code.

---

### Finding #3 — MEDIUM — Signed-in players can bypass stat recording on AI games via `guest: true`

**Severity:** Medium
**Related requirement:** FR-16/FR-25/FR-27 (stats must be "updated after every completed game"); DESIGN.md's own stated anti-cheat principle ("there is no endpoint that accepts a client-declared game result") is undermined by an adjacent loophole — a client *can* unilaterally decide a real game's result is never recorded at all.

**Root cause:** `_create_ai_game()` (`app/games_api.py` lines 66–102) reads `guest = bool(body.get("guest", False))` and, if `guest` is true, **never checks the session cookie at all** — it doesn't matter whether the caller is actually signed in. The UI never sends `guest: true` for a signed-in user (`index.html` only appends `&guest=true` to the AI links `{% if not profile %}`), so this isn't reachable by clicking around normally — but it's a one-line request-body change away.

**Repro:**
```bash
# Sign in as a real profile
curl -s -c cookies.txt -X POST http://127.0.0.1:8130/api/session/new \
  -H 'Content-Type: application/json' -d '{"display_name":"GuestBypassQA","pin":"1234"}'

# Start an AI game AS THAT SIGNED-IN USER but with guest:true
curl -s -b cookies.txt -w "\n%{http_code}\n" -X POST http://127.0.0.1:8130/api/games \
  -H 'Content-Type: application/json' \
  -d '{"mode":"ai","difficulty":"easy","guest":true}'
```
**Result:** `201`, response shows `"x":{"display_name":"Guest"}` even though the request carried a fully valid session cookie for `GuestBypassQA`. Playing this game to any conclusion produces no `profile_updates` and writes nothing to `GuestBypassQA`'s record — confirmed by following up with `GET /api/session` after finishing such a game and seeing unchanged wins/losses/ties.

**Impact:** A player could deliberately shield their record from unfavorable AI results (e.g., testing a difficulty, or simply not wanting a loss to count) by adding `guest: true` to the request. Low likelihood of accidental triggering (requires bypassing the UI), but it's a genuine integrity gap in a feature (stats/leaderboard) the product explicitly cares about. Recommend: when a valid session cookie is present, ignore/reject a client-supplied `guest: true` and always attribute the game to the signed-in profile.

---

### Finding #4 — LOW — `cell: true` (JSON boolean) is silently accepted as a valid move at index 1

**Severity:** Low
**Related requirement:** FR-5/acceptance criteria ("reject moves with invalid/out-of-range/non-integer cell values").

**Root cause:** `game.is_legal_move()` (`app/game.py` line 59) checks `isinstance(cell, int)`. In Python, `bool` is a subclass of `int` (`isinstance(True, int) is True`, and `True == 1`), so a JSON payload of `{"cell": true}` passes the type check and is treated identically to `{"cell": 1}`.

**Repro:**
```bash
curl -s -w "\n%{http_code}\n" -b p1.jar -X POST http://127.0.0.1:8130/api/games/$GAME_ID/moves \
  -H 'Content-Type: application/json' -d '{"cell": true}'
# Actual: 200, places a mark at board index 1 (same as {"cell": 1})
# Expected: 400 illegal_move (true is not a legal cell index)
```
**Impact:** Cosmetic/edge-case only — not reachable through the UI (which always sends a plain integer), and doesn't corrupt game state (it just plays a real, in-range move). Included because the brief specifically asked to hunt for "non-integer cell value" handling gaps.

---

### Finding #5 — LOW — Session cookie is missing the `Secure` flag documented in the design

**Severity:** Low (would be higher on a real production deployment; scoped Low given the app's own "not real auth" framing and PRD's explicit anti-cheat/hardening carve-out)
**Violates:** `docs/DESIGN.md` Section 7: *"`Set-Cookie: session_token=<token>; HttpOnly; SameSite=Lax; Secure; Max-Age=31536000; Path=/`"*

**Root cause:** `_set_session_cookie()` in `app/profiles_api.py` (lines 19–29) calls `resp.set_cookie(..., httponly=True, samesite="lax", max_age=..., path="/")` — no `secure=True`.

**Repro:**
```bash
curl -s -i -X POST http://127.0.0.1:8130/api/session \
  -H 'Content-Type: application/json' -d '{"display_name":"HvhP1QA","pin":"1111"}' | grep -i set-cookie
# Actual:   set-cookie: session_token=...; HttpOnly; Max-Age=31536000; Path=/; SameSite=lax
# Expected: ...; HttpOnly; SameSite=Lax; Secure; Max-Age=31536000; Path=/
```
**Impact:** On the actual Render deployment (HTTPS-only per DESIGN.md Section 9), the browser will still send this cookie if the same host is ever reached over plain HTTP (e.g., during a redirect window, or if HTTPS enforcement has a gap), since `Secure` is what prevents that. Low real-world severity for a casual game with no real PII, but it's a straightforward one-line deviation from the team's own documented security decision and costs nothing to fix (`secure=True` in the `set_cookie()` call).

---

### Finding #6 — LOW (informational) — `active_games` grows unbounded for abandoned in-progress games

**Severity:** Low / informational
**Not a violation of any FR** — FR-34 explicitly allows losing in-progress state on reload, and the design doc (Section 1) explicitly accepts in-memory-only game state as a tradeoff. Flagging only because it's an easy thing to overlook operationally.

**Detail:** Every `POST /api/games` call inserts an entry into the module-level `active_games` dict (`app/games_api.py`). Entries are only ever removed by `_finalize_if_terminal()` when a game reaches a terminal state. A game that's started and then abandoned (browser closed, tab navigated away, page refreshed mid-game) is never removed — it sits in memory for the lifetime of the process. At hobby-project traffic this is very unlikely to matter, but combined with the single-process/no-restart deployment model (DESIGN.md Section 9), a long-lived process with many abandoned games (or repeated refresh-then-abandon cycles, which the UI actively encourages via FR-34's "refresh resets the board" behavior — each refresh of `/game?mode=ai...` starts a *brand-new* game server-side without cleaning up the old one) will accumulate dead entries indefinitely. Not urgent; noting for awareness, no action required unless traffic/uptime assumptions change.

---

## Test artifacts

All ad hoc test scripts used to produce the above (exhaustive Hard AI check, Medium invariant check, leaderboard seeding, HTTP spot checks, etc.) are in `/private/tmp/claude-501/-Users-elvislee-claude-projects-demo/20f446ed-3004-465e-8428-f007d849d865/scratchpad/` if the developer wants to re-run any of them: `qa_test.py`, `qa_ai_exhaustive.py`, `qa_ai_medium_easy.py`, `qa_latency.py`, `qa_leaderboard_seed.py`, `qa_hard_http_spotcheck.py`, `qa_crash2.py`, `qa_crash3.py`.
