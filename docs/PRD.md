# Product Requirements Document: Tic Tac Toe Online

**Status:** Draft for Architect review
**Owner:** Product Manager
**Last updated:** 2026-08-01

---

## 1. Overview / Goal

Tic Tac Toe Online is a web-based rebuild of classic Tic Tac Toe that anyone can play at a public URL. It supports two modes — human vs. AI (three difficulty levels, up to an unbeatable "Hard" AI) and human vs. human on a shared screen — plus a lightweight profile system so players can track their personal win/loss/tie record and compete on a global top-10 leaderboard. The goal is to take a simple single-machine game and turn it into a small but real online product: a live site backed by a real server and database, simple enough for a hobbyist-scale project but built the way a professional team would build it (clear requirements, defined scope, testable acceptance criteria).

---

## 2. User Stories

| # | Story |
|---|-------|
| U1 | As a new player, I want to create a profile with a display name and PIN, so that my game results are saved under my identity. |
| U2 | As a player, I want to play a game against the AI on Easy difficulty, so that I can enjoy a low-pressure, casual game. |
| U3 | As a player, I want to play against the AI on Medium difficulty, so that I get a reasonable challenge without facing a perfect opponent. |
| U4 | As a player, I want to play against the AI on Hard difficulty, so that I can test myself against a maximally skilled opponent (and confirm I can at best tie). |
| U5 | As a player, I want to play a local two-player game against a friend on the same device, so that we can compete head-to-head in person. |
| U6 | As a player, I want to see my own win/loss/tie stats, so that I can track my progress over time. |
| U7 | As a player, I want to view the leaderboard, so that I can see how I rank against the best players. |
| U8 | As a returning player on the same browser, I want to be automatically recognized, so that I don't have to log in again every visit. |
| U9 | As a returning player on a new browser or device, I want to sign back into my existing profile using my name and PIN, so that my stats follow me anywhere. |
| U10 | As a player, I want clear feedback on illegal actions (e.g., wrong PIN, taken name), so that I understand what went wrong and how to fix it. |

---

## 3. Functional Requirements

Numbered for traceability; QA should be able to write test cases directly against each item.

### 3.1 Core Game Rules

| # | Requirement |
|---|-------------|
| FR-1 | The game board is a 3x3 grid. Players alternate placing their mark (X or O); X always moves first. |
| FR-2 | A player wins by placing three of their marks in a row: any full row, any full column, or either diagonal. |
| FR-3 | The game ends in a tie if all 9 cells are filled and no player has achieved a winning line. |
| FR-4 | The game must detect and announce a win or tie immediately after the move that produces it — no further moves are accepted once the game has ended. |
| FR-5 | A player cannot place a mark on a cell that is already occupied. |
| FR-6 | At the end of a game (win, loss, or tie), the outcome is recorded against the participating profile(s) per FR-16, and the player is offered the option to start a new game. |

### 3.2 Game Modes

| # | Requirement |
|---|-------------|
| FR-7 | The player must choose a mode before starting a game: "vs AI" or "vs Human (local)." |
| FR-8 | In "vs AI" mode, the player must select a difficulty (Easy, Medium, Hard) before the game starts. |
| FR-9 | In "vs Human (local)" mode, both participants play from the same device/screen, taking turns; no second device or network handoff is required. |
| FR-10 | In "vs Human (local)" mode, both players must be signed in to a profile before the game starts, so results can be attributed to each (see FR-17 for guest handling). |

### 3.3 AI Behavior

| # | Requirement |
|---|-------------|
| FR-11 | **Easy**: The AI's move selection must be clearly weaker than optimal — e.g., primarily random legal moves, with no deliberate blocking or winning strategy. It should lose regularly against a competent player. |
| FR-12 | **Medium**: The AI must play better than Easy but not optimally — e.g., it takes obvious/immediate wins and blocks obvious/immediate opponent wins, but does not plan further ahead than that (does not force multi-move traps). A skilled player should be able to beat Medium at least some of the time. |
| FR-13 | **Hard**: The AI must play optimally (e.g., via minimax or equivalent). It must never lose — a perfectly-played game against Hard ends in a tie, and any suboptimal human move can be exploited into an AI win. |
| FR-14 | AI move latency should feel immediate to the player (target: AI responds within 1 second of the human's move) so gameplay doesn't stall. |

### 3.4 Accounts / Profiles

| # | Requirement |
|---|-------------|
| FR-15 | A profile consists of: a display name (unique, case-insensitive) and a PIN. See Section 5 for recommended length/character constraints. |
| FR-16 | Per profile, the system tracks and persists: total wins, total losses, total ties, updated after every completed game (ties count for both/all participants when applicable). |
| FR-17 | A player may play "vs AI" without a profile (as a guest); guest results are not saved anywhere. "vs Human (local)" requires both participants to have profiles, since results must be attributed to two distinct records. |
| FR-18 | **Creating a profile**: if the entered display name does not already exist, the system creates a new profile with the given name and PIN. |
| FR-19 | **Name collision, correct PIN**: if the entered display name already exists and the entered PIN matches, the system signs the player into that existing profile (this is the normal "returning player on a new device" flow). |
| FR-20 | **Name collision, wrong PIN**: if the entered display name already exists and the entered PIN does not match, the system rejects the attempt with a clear error (e.g., "That name is taken — enter the correct PIN or choose another name") and does not create or modify any profile. |
| FR-21 | **Validation**: empty/whitespace-only names are rejected. PINs that don't meet the format rules (see Section 5) are rejected. Validation errors are shown before any account action is attempted. |
| FR-22 | **Auto-recognition**: on the same browser, once a player has signed in, the site remembers their identity (e.g., via a local browser token) and skips the name/PIN entry on future visits until they explicitly sign out or switch profiles. |
| FR-23 | A player can explicitly "sign out" / "switch profile" to enter a different name+PIN combination without clearing their browser data. |
| FR-24 | The PIN is never displayed back to the player in plain text after creation (e.g., masked input field), and is not shown anywhere in the UI post-creation. |

### 3.5 Stats

| # | Requirement |
|---|-------------|
| FR-25 | A signed-in player can view their own current wins/losses/ties at any time (e.g., on a profile or stats page). |
| FR-26 | Stats update immediately (visible on the very next view) after a game concludes. |
| FR-27 | Stats are per-profile and global across all game modes/difficulties (i.e., a win vs. Easy AI and a win vs. another human both count as a "win" — the PRD does not require splitting stats by mode/difficulty in v1; see Section 5 for discussion). |

### 3.6 Leaderboard

| # | Requirement |
|---|-------------|
| FR-28 | The leaderboard displays the top 10 ranked players site-wide, publicly viewable without signing in. |
| FR-29 | Ranking metric and tie-breaking rules: see Section 5 (recommendation provided; final call needed). |
| FR-30 | If fewer than 10 players have any recorded games, the leaderboard shows however many qualify (no placeholder/empty rows). |
| FR-31 | Players with zero completed games are not shown on the leaderboard (avoids a wall of 0-0-0 ties at the top under a naive ranking). |
| FR-32 | The leaderboard indicates each player's rank, display name, and the stats that back the ranking (e.g., wins, losses, ties, and the computed score if applicable). |
| FR-33 | If the signed-in player is not in the top 10, the UI should still let them see their own rank/stats (e.g., a "your rank" indicator) — recommended, see Section 5. |

### 3.7 Session / Reload Behavior

| # | Requirement |
|---|-------------|
| FR-34 | Refreshing the page during an in-progress local game (vs AI or vs Human) may reset the current board — in-progress game state is not required to persist across reload in v1 (see Section 4). Completed-game results already recorded before the reload are unaffected. |
| FR-35 | Refreshing or revisiting the site does not require the player to re-enter their name/PIN if FR-22's auto-recognition token is still valid. |
| FR-36 | If a player's local recognition token is missing/invalid/cleared (e.g., new browser, cleared cookies), they are prompted to sign in via name+PIN and can recover their existing profile per FR-19. |

---

## 4. Out of Scope for This Version

To keep the project scoped and prevent silent creep, the following are explicitly **not** being built in v1:

- Real authentication (passwords, email/username login, OAuth/social login).
- Email verification, password reset, or any "forgot my PIN" recovery flow (see Section 5 for the tradeoff this creates).
- Real-time cross-device human-vs-human play (two players on two different devices/browsers playing the same live game). Human-vs-human is same-device/same-screen only.
- Spectator mode or watching other people's live games.
- In-game chat or messaging.
- Native mobile apps (site should be usable in a mobile browser, but no App Store/Play Store builds).
- Friends lists, private messaging, or social/follow features.
- Tournament brackets or matchmaking queues.
- Larger/variant board sizes (e.g., 4x4, Ultimate Tic Tac Toe) — standard 3x3 only.
- Persisting in-progress (unfinished) game state across a page reload or across devices.
- Admin moderation tools (e.g., renaming/banning/deleting other players' profiles) — not needed at this scale.
- Anti-cheat/rate-limiting hardening beyond basic input validation.
- Per-mode/per-difficulty stat breakdowns (e.g., "wins vs Hard AI only") — stats are aggregated globally in v1.

---

## 5. Open Questions / Recommendations

These are items the user or Architect should weigh in on. Each has a recommended default so work isn't blocked.

| # | Question | Recommendation |
|---|----------|-----------------|
| Q1 | **Leaderboard ranking metric** — total wins vs. win rate vs. a composite score? | Total wins is the simplest and most intuitive for a casual game, but it rewards volume over skill (someone who plays 500 games and wins 100 outranks someone who plays 10 and wins 9). A pure win-rate metric is easy to game with a tiny sample (1 win, 0 losses = 100%). **Recommended default: a composite score = wins − losses, with a minimum-games-played threshold (e.g., 5 completed games) to qualify for the leaderboard**, ranked descending by score. Tie-break by (1) higher win count, then (2) earlier account creation date (rewards established players). This balances skill and activity without being gameable by a single lucky game. Flag to revisit if it doesn't feel right once real data exists. |
| Q2 | **Hard AI algorithm** — what "unbeatable" approach? | Recommend the **minimax algorithm** (optionally with alpha-beta pruning for speed, though on a 3x3 board it's not strictly necessary — the full game tree is small). This is the standard, well-understood way to guarantee optimal play. Architect should confirm implementation approach, but the *product requirement* is simply: Hard AI never loses. |
| Q3 | **Medium AI algorithm** — how exactly "better than Easy, worse than Hard"? | Recommend a simple heuristic, not minimax-with-limited-depth (to avoid an accidentally-perfect AI): (1) if Medium can win this move, take it; (2) else if the opponent can win next move, block it; (3) else pick randomly among remaining legal moves (optionally weighting center/corners over edges). This is easy to reason about, easy for QA to test, and reliably produces "beatable but not trivial." |
| Q4 | **Name/PIN format rules** | Recommend: display name 3–20 characters, letters/numbers/underscore/hyphen only (no spaces or special characters, to keep display and URL-safety simple), case-insensitive uniqueness. PIN: exactly 4 digits, numeric only (matches the user's "e.g. 4 digits" framing and keeps entry fast/simple, similar to a bank card PIN). Not intended to be cryptographically secure — this is a casual-game identity mechanism, not an auth system (see Q5). |
| Q5 | **No PIN recovery — what happens if a player forgets their PIN?** | Since there's no email/password, a forgotten PIN currently means **permanent loss of access to that profile's history** — the player would need to create a new profile under a different name. Recommend accepting this tradeoff explicitly for v1 given the "lightweight, not full auth" requirement; it should be stated in the UI at profile-creation time (e.g., "Remember your PIN — there's no way to recover it") so players aren't surprised later. |
| Q6 | **Leaderboard: showing the current player's own rank if outside top 10** | Recommend yes (FR-33) — even a simple "You're ranked #47" line under the top-10 table meaningfully improves the experience for the majority of players who won't crack the top 10, at low implementation cost. Architect to confirm this doesn't materially complicate the leaderboard query. |
| Q7 | **What counts toward stats: AI games, human games, or both?** | Recommend **both count**, undifferentiated (per FR-27), since the user asked for "wins, losses, and ties" without qualification and splitting by mode adds UI/schema complexity for v1. This can be revisited as a v2 enhancement (e.g., "wins vs Hard AI" as a bragging-rights stat). |
| Q8 | **Ties in human-vs-human and vs-AI: how do they count?** | Recommend a tie increments the "ties" counter for every participating profile (both humans in local mode; the human only in vs-AI mode, since the AI has no profile/stats). |
| Q9 | **Minimum games to appear on leaderboard at all** | Covered under Q1's recommendation (5-game minimum) — flagged separately here in case the user wants a different threshold (e.g., 3, or none). A threshold of 0 risks a leaderboard dominated by a single lucky win with a 100% or +1 score. |

---

## 6. Acceptance Criteria Summary (for QA)

This PRD's Functional Requirements (Section 3) are written to be directly testable. At minimum, QA's test plan should cover:

- All 8 winning line combinations (3 rows, 3 columns, 2 diagonals) are correctly detected for both X and O.
- Full-board-no-winner correctly resolves as a tie, not a stuck/undefined state.
- Occupied cells reject further input.
- Easy AI does not always block/win; Medium AI always takes an immediate win/block when available; Hard AI cannot be beaten by any move sequence (only tied).
- Profile creation, correct-PIN sign-in, wrong-PIN rejection, and duplicate-name-different-PIN rejection all produce the correct outcome and user-facing message.
- Empty name, empty PIN, and malformed PIN are all rejected with clear errors before hitting the backend where feasible.
- Stats increment correctly and immediately after win/loss/tie, for both AI and local human-vs-human games.
- Leaderboard returns correctly ranked, correctly tie-broken results, respects the top-10 cap, and degrades gracefully with fewer than 10 (or fewer than the qualifying minimum) players.
- Returning to the site in the same browser skips sign-in; clearing the recognition token (or using a new browser) prompts sign-in and correctly recovers the existing profile via name+PIN.
