# Technical Design Document: Tic Tac Toe Online — v2

**Status:** For Developer implementation
**Owner:** Architect
**Source of truth for requirements:** `docs/PRD_V2.md` (this document makes the implementation decisions PRD_V2 deliberately left to the Architect)
**Baseline architecture:** `docs/DESIGN.md` — v1's shipped, QA'd, production architecture (single FastAPI process on Render, Turso-hosted SQLite-dialect DB, session-cookie identity, Jinja2 + vanilla JS, in-memory `active_games`). **This document does not restate v1 — it specifies deltas.** Anything not mentioned here (AI implementation, v1 schema, v1 endpoints, v1 identity mechanism, hosting choice) is unchanged; read `DESIGN.md` first.
**Last updated:** 2026-08-08

---

## 0. What v2 changes architecturally, at a glance

| Area | v1 | v2 |
|---|---|---|
| Outbound email | None | New: transactional email for PIN reset only (Section 1) |
| Cross-device game state | Didn't exist | New: DB-backed (`live_games` table), not in-memory — see Section 2, this is the one genuine architecture shift |
| Live updates | None needed (request/response only) | Client-side polling against the existing JSON-API pattern (Section 2) — **not** WebSockets/SSE |
| Single-process constraint | Load-bearing for the whole app | Survives v2, but narrows to only v1's in-memory local/AI game path (Section 2.6) |
| CSS | One hand-written stylesheet | Restructured into a small hand-written token+component system, still no build step (Section 3) |
| Local (same-device) human-vs-human | FR-9 | Unchanged, kept as-is (FR-58) |

---

## 1. PIN Recovery (U11–U13, FR-37–FR-43)

### 1.1 Resolving a tension between FR-42 and FR-43

Worth flagging before the design, since the PRD leaves it implicit: FR-43 says recovery must never reveal whether a name has recovery configured (anti-enumeration), while FR-42 says a profile with **no** recovery on file must be told so **plainly**. Read literally these conflict — telling someone "this profile has no recovery configured" necessarily confirms the profile exists.

**Resolution (treated as a deliberate, narrow carve-out, the same pattern the PRD itself uses in Q5 for the leaderboard-name leak):** the "no recovery configured" message is the *only* case that's allowed to be specific. Every other outcome — name doesn't exist, name exists with recovery configured but the submitted email doesn't match — collapses to one identical, generic response. This satisfies FR-43's actual intent (don't let recovery attempts distinguish "exists" from "doesn't exist," or leak *which* email is on file) while still honoring FR-42's explicit ask for plain, actionable messaging in the one case the PRD singled out. See 1.4 for the exact response contract.

### 1.2 Recovery evidence (FR-38, PRD Q1) — concrete mechanic

Q1 recommends "email address, collected once, used solely for reset." Concretely: **the recovery request form collects display name AND the on-file email together, in one step** — the email *is* the "additional piece of recovery evidence" FR-38 requires. A submission only proceeds to actually send anything if both the name resolves to a profile and the submitted email matches that profile's stored `recovery_email` (case-insensitive). This is what makes FR-38's "not on display name alone" requirement concrete, without inventing a second secret (security question) or a second artifact-to-lose (backup code) — consistent with Q1's own reasoning for rejecting (a) and (b).

### 1.3 Schema additions

```sql
-- Additive column on the existing v1 `profiles` table (DESIGN.md Section 3). Nullable — NULL means
-- "no recovery configured," which is the normal state for every pre-v2 profile (FR-42) and for anyone
-- who skips the optional field at signup.
ALTER TABLE profiles ADD COLUMN recovery_email TEXT;

-- One-time-use reset tokens. Separate table (not columns on profiles) because a profile can have at
-- most one *live* token at a time by construction (1.4), but keeping history here is cheap and useful
-- for the same audit-trail reasoning v1 applied to game_results.
CREATE TABLE pin_resets (
    token       TEXT PRIMARY KEY,       -- secrets.token_urlsafe(32), same style as v1 session tokens
    profile_id  INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    expires_at  TEXT NOT NULL,          -- created_at + 30 minutes, computed by the app at insert time
    used_at     TEXT                    -- NULL until consumed; set atomically with the PIN update (1.4)
);
CREATE INDEX idx_pin_resets_profile ON pin_resets(profile_id);
```

**Token:** `secrets.token_urlsafe(32)`, embedded in the emailed link (`{PUBLIC_BASE_URL}/reset-pin?token=...`), never displayed in the UI, never logged. **Expiry: 30 minutes**, a firm default (typical for this kind of flow — long enough to check email, short enough to bound exposure). **Single use**, enforced by `used_at`. On a new recovery request for a profile that already has an unexpired, unused token, the old row is deleted and replaced (only the most recently emailed link ever works) — avoids stale-link confusion and keeps the exposure window tight.

**Lightweight anti-abuse (proportionate, matches v1's "basic validation only" stance):** a 60-second per-profile cooldown between successful sends (checked against the most recent `pin_resets.created_at` for that `profile_id`, regardless of `used_at`) — stops a stranger who knows someone's display name and email from repeatedly bombing their inbox. No IP-based limiting, no CAPTCHA — deliberately not building more than this, same reasoning as v1's PIN-brute-force call.

### 1.4 Endpoints

| Method & Path | Request | Response | Notes |
|---|---|---|---|
| `POST /api/pin-recovery/request` | `{ "display_name": str, "email": str }` | `200 { status: "sent_if_eligible" \| "not_configured", message: str }` | See below for exactly which case produces which `status`. |
| `GET /reset-pin?token=...` | — | Jinja2 page: new-PIN form, or a plain "this link is invalid or expired" page if the token is missing/unrecognized/expired/used (checked server-side before rendering the form) | Page route, not JSON API — this is where the emailed link lands. |
| `POST /api/pin-recovery/reset` | `{ "token": str, "new_pin": str }` | `200 { ok: true }` on success; `400 { error: "invalid_or_expired_token" }` otherwise | On success: validates `new_pin` format (v1 Q4 rule, 4 digits), then in **one transaction**: updates `profiles.pin_hash`/`pin_salt`, sets `pin_resets.used_at`, and **deletes all `sessions` rows for that `profile_id`**. |

`POST /api/pin-recovery/request` logic, resolving 1.1:
1. Look up `profiles` by `display_name`. Not found → `{status: "sent_if_eligible", message: "If that matches an account with recovery configured, we've emailed a reset link."}` (generic, no send happens).
2. Found, `recovery_email IS NULL` → `{status: "not_configured", message: "This profile doesn't have PIN recovery set up. If this is your profile, you'll need to create a new one — see PRD v1 Q5."}` (FR-42's carve-out, distinguishable by design).
3. Found, `recovery_email` set but doesn't match the submitted `email` (case-insensitive) → same generic `sent_if_eligible` response as case 1 (no send). This is what makes cases 1 and 3 indistinguishable to the caller, satisfying FR-43.
4. Found and email matches, and the 60s cooldown isn't active → generate a token (1.3), send the email (1.5), return the same generic `sent_if_eligible` response as cases 1 and 3 — **the true-positive response is worded and shaped identically to the "nothing happened" responses.** This is the standard pattern for anti-enumeration reset flows and is what actually delivers FR-43, not just the messaging.
5. Found, email matches, but cooldown active → same generic response as case 4, silently skip the send.

The extra logout-all-sessions step in the reset endpoint is beyond what any FR explicitly asks for, but costs one `DELETE` and closes an obvious gap (a reset implies the old PIN may have leaked or been forgotten under suspicious circumstances; kicking existing sessions is cheap, proportionate hardening, same spirit as v1's PIN-hashing decision).

### 1.5 Email service — Decision: Resend

| Option | Verdict | Why |
|---|---|---|
| **Resend** | **Chosen** | Free tier: 3,000 emails/month, 100/day — enormous headroom for a PIN-reset flow at hobby scale. No credit card for the free tier. Simple, modern API with an official Python SDK (`resend` on PyPI), a few lines to send an email. Still a live, indefinite free tier as of 2026. |
| SendGrid | Rejected | Twilio retired SendGrid's permanent free plan in 2025 — new signups now get a 60-day trial only, then it's paid. Doesn't meet "free for a hobby project" durably. |
| AWS SES | Rejected | Technically cheap ($0.10/1,000 emails) but not free, and not simple: requires an AWS account, IAM setup, and — critically — new accounts start in a **sandbox** that can only send to individually pre-verified recipient addresses until you request "production access" (a manual AWS approval process). That sandbox restriction defeats the point (needs to email arbitrary real users), and the approval step is disproportionate friction for a hobby project. |

**Real prerequisite worth flagging clearly (this is general to transactional email, not a Resend-specific downside):** sending to arbitrary real recipients — as opposed to only the developer's own inbox — requires a **verified sending domain** (DNS records: SPF/DKIM, configured once in Resend's dashboard). Without one, Resend's free tier restricts sending to the account owner's own verified address only — fine for development, useless for real users. This means the actual new cost of this feature isn't Resend (which is $0) — it's **owning a domain** to verify (typically ~$10–15/year if one isn't already owned) plus a one-time DNS setup. This is unavoidable with any provider (SES has the identical sandbox restriction until production access is granted); it isn't something a different vendor choice avoids. Flagged again in Section 6/7.

Email content (plain, not templated HTML needed): subject "Reset your Tic Tac Toe Online PIN," body states the reset link, the 30-minute expiry, and — directly satisfying U12 — one explicit sentence that this is not a secure recovery method on the same trust level as real auth, matching the PRD's "tell the player plainly what they're trading off" framing.

---

## 2. Real-Time Cross-Device Human-vs-Human (U14–U19, FR-44–FR-60)

### 2.1 Live-update mechanism — Decision: client-side polling, not WebSockets or SSE

**Chosen:** the client polls `GET /api/live-games/{id}` on a fixed interval (2 seconds) while a cross-device game is open and the tab is visible (paused via the Page Visibility API when backgrounded, to avoid wasted requests). This is the same request/response JSON-API pattern v1 already established — no new server-side connection model.

**Rejected: WebSockets.** The textbook answer for "real-time," and FastAPI supports it natively, but disproportionate here for three concrete reasons:
1. Tic-tac-toe is human-paced — moves are seconds to minutes apart. FR-53's actual bar is "no manual refresh," not low-latency; a 2-second poll clears that bar with room to spare.
2. WebSockets need in-process connection-lifecycle management (tracking open sockets per game/player) plus reconnect-with-backoff logic on the client, and a ping/pong heartbeat to survive Render's free-tier proxy idle timeouts — real new complexity for a solo hobbyist, for a latency improvement the game doesn't need.
3. It would still need the *state* to live in the DB anyway for reconnection (2.3), so WebSockets wouldn't remove the DB-backed design below — they'd only add a second, parallel transport on top of it.

**Rejected: Server-Sent Events.** Same connection-lifecycle and Render-proxy-timeout concerns as WebSockets, for a narrower win (SSE is server→client only, so submitting a move still needs a separate POST) — worse cost/benefit than either polling or WebSockets.

**Why polling is a genuinely good fit here, not just "the cheap option":** disconnect detection (FR-54) and reconnection (FR-56) both fall out of the same mechanism for free — see 2.4 and 2.3 — instead of needing a separate heartbeat protocol invented on top of a push transport. One mechanism does double duty as "deliver moves" and "prove the player is still there."

### 2.2 Challenge / invite flow (FR-44–FR-49, U14, U15, U18)

```sql
CREATE TABLE challenges (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    challenger_id  INTEGER NOT NULL REFERENCES profiles(id),
    invitee_id     INTEGER NOT NULL REFERENCES profiles(id),
    status         TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending','accepted','declined','cancelled','expired')),
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    expires_at     TEXT NOT NULL,        -- created_at + 5 minutes (Architect default, see note below)
    game_id        INTEGER REFERENCES live_games(id)   -- set once accepted
);
-- FR-49: at most one *pending* outgoing challenge per (challenger, invitee) pair.
CREATE UNIQUE INDEX idx_challenges_pending_pair
    ON challenges(challenger_id, invitee_id) WHERE status = 'pending';
```

**Firm default not actually specified in PRD_V2 despite the FR-48 cross-reference:** Section 5 of PRD_V2 doesn't give a concrete expiry duration for a pending challenge (Q1–Q6 cover other things). Architect default: **5 minutes** — long enough that an invitee already browsing the site has a real chance to see and act on the badge (2.2.1), short enough that stale invites (FR-48's concern) don't linger. Revisit with the PM if it feels wrong once there's real usage.

**FR-49 ("replaces, not stacked"):** a new challenge from the same challenger to the same invitee while one is already pending **updates** the existing row's `created_at`/`expires_at` (resets the clock) rather than erroring or inserting a second row — friendlier than rejecting, and the unique partial index above makes "only one pending row per pair" trivially enforced at the DB level regardless.

**Expiry enforcement:** lazy, on-touch — same pattern as v1's server-authoritative philosophy, no scheduler needed. Any read or accept/decline attempt checks `expires_at < now` first and treats it as expired (opportunistically flipping `status` to `'expired'` so the unique-pending-index frees up for a future challenge between the same pair). Render's free tier has no convenient always-on free cron primitive, so avoiding a scheduled sweep entirely is a deliberate, not accidental, choice.

#### 2.2.1 How the invitee finds out (FR-46, PRD Q2)

Per Q2's recommendation (in-product only, no email/push): `GET /api/challenges` returns `{ incoming: [...], outgoing: [...] }` for the signed-in profile. The nav bar (present on every page per v1's shared base template) polls this endpoint every ~10 seconds (a much lower frequency than the in-game 2s poll — there's no live-game urgency here, just "is there anything waiting for me") and shows a badge count when `incoming` is non-empty. The same endpoint backs a dedicated "Challenges" page listing each with Accept/Decline (invitee) or Cancel (challenger) actions.

Endpoints:

| Method & Path | Request | Response | Auth rule |
|---|---|---|---|
| `POST /api/challenges` | `{ "invitee_name": str }` | `201 { challenge_id, invitee_name, status: "pending", expires_at }` | Requires session cookie. Invitee must exist and not equal the caller (else a generic failure, per PRD Q5's accepted minor leak — a successful send does confirm the name exists, same as v1's leaderboard names being semi-public). |
| `GET /api/challenges` | — | `200 { incoming: [...], outgoing: [...] }` | Requires session cookie; scoped to the caller only. |
| `POST /api/challenges/{id}/accept` | — | `201 { game_id }` | Caller must be `invitee_id`; challenge must be `pending` and unexpired; caller must not already be in an `in_progress` `live_games` row (FR-59) — else `409`. Creates the `live_games` row (2.3), sets `status='accepted'`, `game_id`. |
| `POST /api/challenges/{id}/decline` | — | `204` | Caller must be `invitee_id`. |
| `DELETE /api/challenges/{id}` | — | `204` | Caller must be `challenger_id`. |

### 2.3 Cross-device game state — Decision: DB-backed (`live_games` table), not in-memory

**This is the one real architecture delta from v1.** v1's `active_games` (in-memory, per-process) is fine for local/AI games because they're short, synchronous, and FR-34 explicitly allows losing that state on reload. Cross-device games are neither: two humans on separate devices can easily leave 10+ minutes between moves, and Render's free tier spins the app down after **15 minutes of idle** — a real, non-hypothetical scenario for a slow-paced casual game, not an edge case. FR-60 also explicitly requires reload-survival, unlike v1's FR-34 allowance. In-memory state cannot satisfy either fact, so it moves to Turso:

```sql
CREATE TABLE live_games (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    x_profile_id    INTEGER NOT NULL REFERENCES profiles(id),   -- challenger (FR-52)
    o_profile_id    INTEGER NOT NULL REFERENCES profiles(id),   -- accepting player (FR-52)
    board           TEXT NOT NULL DEFAULT '_________',
    current_turn    TEXT NOT NULL DEFAULT 'X' CHECK (current_turn IN ('X','O')),
    status          TEXT NOT NULL DEFAULT 'in_progress'
                      CHECK (status IN ('in_progress','x_won','o_won','tie','forfeited_x','forfeited_o')),
    x_last_seen_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    o_last_seen_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ended_at        TEXT
);
CREATE INDEX idx_live_games_x ON live_games(x_profile_id);
CREATE INDEX idx_live_games_o ON live_games(o_profile_id);
```

No `'abandoned'` status — per PRD Q3's firm recommendation, every disconnect resolves to a forfeit (2.4), never an unscored abandonment, so the model doesn't need to represent that case.

**On completion** (any terminal status), the same finalize step v1 already has is reused unchanged: insert into the existing `game_results` table (`mode='human'`, `difficulty=NULL`, exactly as v1's local human-vs-human already does) and increment both profiles' counters — forfeits count as a real loss/win, not a wash, per Q3. **No schema change needed to `game_results` at all** — cross-device results roll into the same table and the same stats bucket as local human games, which is also exactly what PRD_V2 Section 4 asks for (no per-mode stat split). This is a direct payoff of v1's schema having kept `game_results` generic rather than coupling it to "local games" specifically.

**Reconnection (FR-56)** is close to free with this design: the live-game page URL is `/play/live/{game_id}`; reloading it just re-runs `GET /api/live-games/{id}` using the ID already in the URL. No server-side "session resume" logic is needed beyond normal bookmarkable URLs plus the authorization check in 2.5. For a player who navigates away entirely (not just reloads), `GET /api/live-games/current` returns their one `in_progress` game if any, so a "Resume game" banner can be shown from the home/profile pages — reusing the same badge-style pattern as pending challenges.

**Authorization (FR-57 — hard boundary, not a low-stakes accepted risk):** unlike v1's guest/local games, which rely on `game_id` unguessability, `live_games` endpoints check the session cookie's `profile_id` against `x_profile_id`/`o_profile_id` on the row and reject (`403`) anyone else — real authorization, not obscurity, because FR-57 explicitly makes spectating a hard boundary rather than an accepted low-stakes risk.

Endpoints:

| Method & Path | Request | Response | Notes |
|---|---|---|---|
| `GET /api/live-games/{id}` | — | `200 { game_id, board, current_turn, status, winner, winning_line, opponent_state: "connected"\|"stale"\|"forfeited" }` | The poll endpoint (2.1). Also: (a) updates the caller's own `*_last_seen_at` (this *is* the heartbeat, 2.4), and (b) runs the lazy staleness/forfeit check (2.4) before responding. `403` if caller isn't a participant (FR-57). |
| `POST /api/live-games/{id}/moves` | `{ "cell": 0-8 }` | Same shape as above | Same authoritative-server pattern as v1: validates it's the caller's turn, applies the move, checks win/tie via the same `game.py` win-check used everywhere else, finalizes on terminal state. Runs the same staleness check first (a stale opponent shouldn't be able to out-race a forfeit with a last-second move after the grace period's already elapsed). |
| `GET /api/live-games/current` | — | `200 { game_id } \| 204` | Powers the "resume game" affordance (FR-56). |

`winning_line` (e.g. `[0,1,2]`) is a small, worthwhile addition to the terminal response — computed once server-side from the same `LINES` table `game.py` already has (DESIGN.md Section 5), so the frontend doesn't re-derive it; it directly feeds FR-62's "highlight the winning line" requirement (Section 3).

### 2.4 Disconnect detection & auto-forfeit (FR-54, FR-55, U17, PRD Q3)

No WebSocket close event, no separate heartbeat endpoint — the poll itself *is* the heartbeat, via `*_last_seen_at`. Three thresholds, all derived from the 2-second poll interval and PRD Q3's 2-minute grace-period recommendation:

- **< 20s since last seen:** `opponent_state: "connected"`.
- **20s–120s:** `opponent_state: "stale"` — U17's "let me know something might be wrong" signal, shown as a "reconnecting…" indicator without ending the game (tolerates a brief phone-lock or dropped wifi, per Q3's own reasoning for why 2 minutes and not something shorter).
- **> 120s (the grace period):** resolved **lazily**, the next time *either* participant's request touches this `game_id` (a poll or a move) — not via a background job (Render's free tier has no convenient always-on cron; consistent with the same choice made for challenge expiry in 2.2). The stale player's mark forfeits (`forfeited_x`/`forfeited_o`), stats are recorded as a real loss/win exactly like any other completed game (2.3, per Q3), and the connected player's next poll reports the outcome.

**Known, accepted edge case:** if *both* players stop returning entirely, nothing ever touches the row again, so it never gets the lazy resolution and technically stays `in_progress` forever. In practice this is inert — one small DB row, no polling loop, no cost, and nobody is around to be bothered by an unresolved outcome they'll never check. Judged sufficient for v2; flagged in Section 7 rather than solved with a scheduled sweep now.

### 2.5 Same-device mode stays (FR-58, U19)

No change: v1's local human-vs-human (`POST /api/games` with `mode: "human"`, DESIGN.md Section 4.2) is untouched and unaffected by any of the above — it's a fully separate code path (`active_games`, in-memory) from the new `live_games` path. Mode selection gains a third option (`vs Human — invite`) that routes to the challenge flow (2.2) instead.

### 2.6 Does the single-process constraint survive v2?

**Yes, but its cause narrows.** In v1, single-process was load-bearing for the *whole app*, because both local/AI game state (in-memory) and SQLite's weak concurrent-writer story depended on it. As of v2's Turso-hosted DB (already true since the v1 persistence revision) and now this section's DB-backed `live_games`, **the new cross-device feature itself has no single-process dependency at all** — any number of Render instances could correctly serve `live_games`/`challenges` traffic against Turso, since polling means every request is independently self-contained (no server-held connection state to lose by hitting a different instance).

The constraint survives v2 for exactly one remaining reason: **v1's local/AI game path still uses the in-memory `active_games` dict.** That's deliberately not being changed in v2 (Section 2.5) — it works, it's simple, and migrating it to the DB purely for symmetry with the new feature would be scope creep with no user-facing benefit. So: still single-process, but now it's an isolated, easily-removable legacy constraint tied to one code path, not a property of the whole architecture. Worth knowing if `active_games` is ever revisited later, but not a reason to change anything now — Render's free web service is single-instance by default anyway.

DESIGN.md Section 1 has been annotated with a pointer to this section (see the diff note at the end of this document).

---

## 3. UI / Visual Design Overhaul (U20–U23, FR-61–FR-68)

### 3.1 Decision: stay within v1's no-build-step approach, but restructure the CSS into a small hand-written token+component system

**Chosen:** still plain CSS, still no npm/bundler/preprocessor, still no external framework (CDN or otherwise) — but split from v1's single stylesheet into:
- `static/css/tokens.css` — CSS custom properties only: color palette, a small type scale, a spacing scale, radii. (`:root { --color-x: ...; --color-o: ...; --space-2: ...; --font-size-lg: ...; }`)
- `static/css/components.css` — reusable classes built from those tokens: `.btn`, `.card`, `.field` (+ `.field-error`), `.badge`, board-cell states, banner variants (win/loss/tie).
- Per-page styles (if any are still needed beyond the shared components) stay minimal and layer on top.

**Why not a framework (Bootstrap/Tailwind/etc.), given the increased scope:** FR-61 ("share one consistent visual system") is fundamentally a *discipline* problem — reuse the same variables and component classes everywhere — not a tooling gap. A framework either requires a build step to customize meaningfully (fighting the standing no-build-step decision for no real gain) or means adopting a large, generic, out-of-the-box visual language via CDN that actively works against FR-62's need for a *specific*, considered design (deliberate X/O color coding, a highlighted winning line, board-specific responsive behavior) and adds an external runtime dependency the project has otherwise avoided entirely. CSS custom properties get the "consistent, structured, easy to reuse" benefit FR-61 actually needs, in a few files, with zero new dependencies — proportionate to the scope increase without crossing into "add a build pipeline," which nothing here actually requires.

### 3.2 Responsive strategy (FR-63)

**One breakpoint, mobile-first:** base styles target the ~375px case directly (not as an afterthought); `@media (min-width: 600px)` layers on desktop refinements (wider centered container, any side-by-side layouts). PRD_V2 only requires "no horizontal scroll / no pinch-zoom at ~375px" — it doesn't ask for tablet-specific tuning, so a single breakpoint is the proportionate choice; a multi-tier breakpoint system would be solving a problem nobody asked for.

**Board sizing, concretely** (this is the mechanism that actually makes FR-63 true for the board specifically, not just a media-query promise): CSS Grid with `aspect-ratio: 1` on the board container and cell sizing in relative units (`vmin`/`%`, not fixed px), so the 3×3 grid scales fluidly to the viewport instead of needing per-breakpoint pixel overrides. Tap targets (cells, buttons) sized with a minimum comfortable touch target (`min-height`/`min-width` from the spacing scale) regardless of viewport, addressing FR-63's "hit tap targets" clause directly.

### 3.3 Turn/outcome clarity (FR-62)

- **Turn indicator:** a persistent, always-visible element ("Your turn (X)" / "Waiting for O…") using a distinct token color per mark, applied consistently to both the indicator text and the marks rendered on the board — color-coded, but the letter (X/O) is always also shown, so it isn't color-alone-dependent (cheap accessibility instinct, not a PRD requirement but free to include).
- **Winning line:** the move endpoint's terminal response now includes `winning_line` (2.3); the frontend applies a distinct highlight class to exactly those three cells — a distinct background/outline, computed from server data rather than re-derived client-side.
- **Win/loss/tie:** a prominent banner above the board with a distinct color+icon per outcome (not just appended text) — satisfies FR-62's "unambiguous at a glance" bar directly.

### 3.4 Interactive/loading/error states (FR-64–FR-66)

- **Disabled/hover/focus:** token-driven states in `components.css` applied uniformly — a filled cell and a mid-request button both get the same `.is-disabled` treatment; keyboard focus gets a visible outline (not suppressed), satisfying FR-64's keyboard-user clause.
- **Loading (FR-66):** one shared convention — on any `fetch()` call in `board.js`/`live-board.js`/`signin.js`/`challenges.js`, the triggering element gets `.is-loading` (a small inline spinner/pulse) immediately and it's removed when the response resolves. Documented once here as the pattern every new JS interaction should follow, rather than specified per-component.
- **Errors (FR-65):** one shared `.field-error` pattern — red-bordered input + inline message directly under the field — used by every form (sign-in, profile creation, forgot-PIN, challenge-send).

### 3.5 Sign-off (FR-68, PRD Q4)

No design changes needed here beyond what Q4 already recommends — a per-FR (FR-61–FR-66) pass/fail checklist reviewed by the stakeholder plus one other person. Noted here only to confirm the Architect isn't adding a different process.

---

## 4. Cross-Cutting: Project Structure Additions

New files/modules on top of v1's tree (DESIGN.md Section 8); nothing listed there is removed or restructured.

```
app/
├── pin_recovery_api.py     # POST /api/pin-recovery/request, POST /api/pin-recovery/reset
├── challenges_api.py        # POST/GET/accept/decline/cancel challenge endpoints (2.2)
├── live_games_api.py         # GET/POST live-game endpoints, incl. /current (2.3)
├── email.py                   # thin Resend wrapper: send_pin_reset_email(profile, token)
├── templates/
│   ├── forgot_pin.html            # name + email form (FR-37)
│   ├── reset_pin.html               # new-PIN form, landed on via the emailed link
│   ├── challenges.html                # incoming/outgoing pending challenges (also feeds nav badge)
│   └── live_game.html                   # cross-device board page (loads live-board.js)
└── static/
    ├── css/
    │   ├── tokens.css        # NEW — design tokens (3.1)
    │   └── components.css    # NEW — shared component classes (3.1)
    └── js/
        ├── board-render.js    # NEW — shared rendering/DOM logic factored out of v1's board.js,
        │                        #       used by both board.js (request/response) and live-board.js
        │                        #       (polling), so FR-62's visual logic lives in exactly one place
        ├── live-board.js       # NEW — polling variant of the board UI (2.1), built on board-render.js
        └── challenges.js        # NEW — polls GET /api/challenges for the nav badge (2.2.1)
```

`board-render.js` is a deliberate refactor, not new scope: without it, FR-62's win/turn/board visuals would need to be implemented twice (once for the request/response local-game flow, once for the polling cross-device flow) and would drift. Factoring the shared rendering logic out once keeps v1's board.js and the new live-board.js both thin wrappers around the same visual behavior.

`requirements.txt` addition: `resend` (official Python SDK).

---

## 5. Cross-Cutting: Deployment Updates

No hosting decision changes — same Render app, same Turso database (new tables added via the same schema-init code path already in `db.py`). This is a direct payoff of the polling decision (2.1): there's no new connection model, proxy configuration, or infrastructure for Render to run differently.

New environment variables (alongside the existing `TURSO_DATABASE_URL`/`TURSO_AUTH_TOKEN`):
- `RESEND_API_KEY` — Resend API key, set as a Render secret.
- `PUBLIC_BASE_URL` — e.g. `https://<name>.onrender.com`, used to build the reset-PIN link (Section 1) explicitly rather than trusting a request `Host` header.

**One real, non-code prerequisite before PIN recovery works for real users (not just the developer's own inbox):** a verified sending domain must be configured in Resend (DNS records) — see 1.5. This needs to happen once, out-of-band, before shipping the recovery feature; it isn't a Render or code change.

---

## 6. Open Items for the Developer

| # | Item | Default | Notes |
|---|---|---|---|
| V1 | Challenge expiry window (FR-48) | 5 minutes | PRD_V2 cross-references Section 5 for this but no concrete number is actually given there — Architect-set default (2.2). Revisit with the PM if real usage suggests otherwise. |
| V2 | Polling intervals (2s in-game, 10s for the challenge badge) | As specified (2.1, 2.2.1) | Tune later only if request volume ever becomes a real cost/load concern — not expected at hobby scale. |
| V3 | True-abandonment edge case: both players in a `live_games` row never return | Accepted, unresolved-in-practice (2.4) | Row stays `in_progress` indefinitely but is inert (no cost, no polling loop). A future periodic sweep would fix this properly but needs a scheduled job; Render's free tier has no convenient built-in cron, so this is deliberately not built now. |
| V4 | Domain + DNS setup for Resend deliverability | Required before recovery works for real users; not a code task | ~$10–15/yr if a domain isn't already owned, one-time DNS configuration. Flagged prominently (1.5, Section 5) so it isn't discovered late. |
| V5 | Recovery-request rate limiting | 60s per-profile cooldown only, no IP-based limiting | Matches v1/v2's standing "no anti-cheat/rate-limiting hardening beyond basic validation" stance. |
| V6 | Whether to eventually move v1's local/AI `active_games` off in-memory for architectural symmetry with `live_games` | **No** — not recommended | Would remove the last reason for the single-process constraint (2.6), but there's no user-facing problem it would solve; flagged only so it's a conscious "not now," not an oversight. |

---

## Appendix: Diff note applied to `docs/DESIGN.md`

DESIGN.md's Section 1 "single process/worker" paragraph now carries a short pointer added alongside it, noting that v2 introduces a DB-backed feature (cross-device play) that does *not* require single-process, and that the constraint's remaining cause is narrowed to v1's in-memory local/AI game path — full reasoning lives here in Section 2.6, DESIGN.md itself is otherwise unchanged and still describes v1's shipped architecture accurately.
