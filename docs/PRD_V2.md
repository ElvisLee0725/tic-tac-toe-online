# Product Requirements Document: Tic Tac Toe Online — v2

**Status:** Draft for Architect review
**Owner:** Product Manager
**Last updated:** 2026-08-08

---

## 1. Overview / Goal

v1 shipped a working live product: AI play (three difficulties), same-device human-vs-human, profiles with a name+PIN identity, personal stats, and a top-10 leaderboard, on a single FastAPI process with a Turso-hosted database. It's been live and stable since.

v2 does not change the game itself (still standard 3x3 Tic Tac Toe — see v1 FR-1–FR-6, unchanged) or the identity model's fundamental shape (still name+PIN, not real auth). It addresses three things the stakeholder has called out after watching v1 in the wild:

1. **PIN recovery** — v1 explicitly accepted "forgot your PIN, lose the profile forever" as a tradeoff (PRD v1 Q5). That's no longer acceptable.
2. **Real-time cross-device human-vs-human** — v1 explicitly restricted human-vs-human to two people at one screen (PRD v1 FR-9, out-of-scope list). The stakeholder wants two people on two different devices to play the same live game.
3. **UI/visual design overhaul** — v1's UI was built functionally, no design pass, plain hand-written CSS. The stakeholder's plain assessment: "the UI is ugly."

This document assumes v1's shipped architecture as ground truth (single FastAPI process, server-rendered Jinja2 + one JS file for the board, SQLite-dialect schema on Turso, in-memory active-game state, session-cookie identity — see `DESIGN.md`). It scopes **requirements**, not implementation; technical approach (e.g., how live updates are delivered, how PIN reset tokens are generated/stored) is the Architect's call next, except where a requirement below inherently implies a constraint the Architect needs to know about up front.

---

## 2. User Stories

### 2.1 PIN Recovery

| # | Story |
|---|-------|
| U11 | As a player who has forgotten my PIN, I want a way to reset it myself without contacting anyone, so that I can recover access to my existing profile's name and stats. |
| U12 | As a player setting up recovery, I want to be told plainly what I'm trading off (e.g., "this reset method is only as secure as X"), so I understand the risk model — this is still not bank-grade auth. |
| U13 | As a player, I want the PIN reset process to fail safely (not let a stranger who doesn't know my PIN take over my profile), so my stats and identity stay mine. |

### 2.2 Real-Time Cross-Device Human-vs-Human

| # | Story |
|---|-------|
| U14 | As a signed-in player, I want to start a live game and invite a specific other player by name, so we can play against each other from our own separate devices. |
| U15 | As the invited player, I want to see that I've been challenged to a game and be able to accept or decline it, so I'm not dropped into a game I didn't agree to. |
| U16 | As a player in an active cross-device game, I want to see my opponent's moves appear on my board automatically (no manual refresh), so the game feels live. |
| U17 | As a player in an active cross-device game, I want to know if my opponent has disconnected or gone quiet, so I'm not left staring at a board wondering if the game is still happening. |
| U18 | As a player who sent or received an invite, I want to cancel/decline it before the game starts, so an unwanted or stale challenge doesn't linger. |
| U19 | As a player, I want to still be able to play human-vs-human on one shared screen if that's more convenient (e.g., we're already in the same room), so the existing same-device mode isn't taken away. |

### 2.3 UI/Visual Design Overhaul

| # | Story |
|---|-------|
| U20 | As a player, I want the site to look and feel visually consistent from page to page, so it feels like one coherent product instead of separately built screens. |
| U21 | As a player, I want the game board and turn/outcome state to be immediately, unambiguously readable at a glance, so I don't have to hunt for whose turn it is or what just happened. |
| U22 | As a player on a phone, I want the site to be comfortably usable — readable text, tappable buttons/cells, no horizontal scrolling or pinch-zooming required — so I'm not limited to playing on a desktop. |
| U23 | As a player, I want clear visual states for interactive elements (buttons, form fields, the board's cells) — hover/focus/disabled/error states — so the UI gives me feedback instead of feeling static or unresponsive. |

---

## 3. Functional Requirements

Numbered continuing from v1 (last was FR-36).

### 3.1 PIN Recovery

| # | Requirement |
|---|-------------|
| FR-37 | A "Forgot your PIN?" path must be reachable from the sign-in screen. |
| FR-38 | Initiating recovery requires the player to supply their exact display name plus one additional piece of recovery evidence established at profile-creation time (see Q1 in Section 5 for what this evidence is — the mechanism itself is an open question deliberately left to Section 5/Architect, not decided here). Recovery must not succeed on display name alone. |
| FR-39 | On successful recovery-evidence verification, the player is able to set a new PIN for that profile. The old PIN immediately stops working. |
| FR-40 | On failed/incomplete recovery (wrong evidence, expired recovery link/code, etc.), the system gives a clear but non-revealing error (consistent with v1 FR-19's philosophy: never confirm/deny whether a given display name exists or has recovery configured). No profile is modified on failure. |
| FR-41 | A recovery attempt (successful or not) does not expose or reset a profile's wins/losses/ties or delete `game_results` history — recovery changes only the PIN. |
| FR-42 | If a profile was created before v2 shipped and has no recovery evidence on file (see FR-38), the player is told plainly that recovery isn't available for that profile (since the "no recovery" tradeoff was accepted at the time it was created) and is directed to create a new profile if truly locked out. This is a one-time migration-era edge case, not a permanent second class of profile — see Section 5 Q1 for how new profiles avoid ever landing in this state. |
| FR-43 | Recovery-in-progress must not be usable to enumerate valid display names or determine whether a name has recovery configured (mirrors v1's FR-19 anti-enumeration stance). |

### 3.2 Real-Time Cross-Device Human-vs-Human

| # | Requirement |
|---|-------------|
| FR-44 | A signed-in player can initiate a cross-device challenge by entering the exact display name of another existing profile. The challenger does not need to know the opponent's PIN (unlike v1's same-device flow, where the second player authenticates themselves directly on the shared device). |
| FR-45 | The challenged player must see the pending challenge and explicitly **accept** or **decline** it before any game/board is created. A game never starts without both players' affirmative participation — the challenger cannot force a game to begin just by sending the invite. |
| FR-46 | Where the challenged player sees a pending invite is an open question for Section 5 (e.g., must they be actively on the site, or does something outside the site notify them) — flagged as a real product decision, not purely technical, since it affects whether U14 is actually usable in practice. |
| FR-47 | A pending (not-yet-accepted) challenge can be cancelled by the challenger or declined by the invitee at any time before acceptance. Cancelled/declined challenges do not create a game and are not scored. |
| FR-48 | A pending challenge expires automatically after a bounded time if neither accepted nor declined (see Section 5 for recommended default), so stale invites don't accumulate indefinitely. |
| FR-49 | A player may not have unlimited simultaneous pending outgoing challenges to the same opponent (e.g., re-challenging before the first is resolved is rejected or replaces the existing one, not stacked) — prevents invite spam to a single player. |
| FR-50 | Once accepted, the game behaves like v1's human-vs-human rules (FR-1–FR-6, FR-10): standard turn alternation, X (the challenger, per FR-52) moves first, win/tie detection, stats recorded identically to v1's local human-vs-human (both profiles' wins/losses/ties update per PRD v1 Q8). |
| FR-51 | Each player only ever sees and acts on their own turn's legal moves on their own device; a player cannot submit a move when it isn't their turn, exactly as v1 already enforces server-side for local play. |
| FR-52 | The challenger is assigned X and moves first; the accepting player is assigned O. (Simple, deterministic, consistent with v1's "human always plays X" convention for vs-AI — see PRD v1 Section 4.2 rules.) |
| FR-53 | While a cross-device game is in progress, each player's board must reflect the opponent's move without the player manually reloading the page. This is a hard functional requirement of "real-time" (U16) — the Architect must select a live-update mechanism; the product requirement is only the observable behavior (move appears without manual refresh), not how. |
| FR-54 | If a player's connection drops or they close the tab mid-game, the other player must be informed (not left indefinitely waiting with no signal) within a bounded, reasonably short time (see Section 5 for a recommended default window). |
| FR-55 | A cross-device game where one player has disconnected must eventually resolve — either the game auto-forfeits to the connected player after a grace period, or it's abandoned unscored (see Section 5 Q3 for the recommendation) — it must not stay "in progress" forever consuming state with no way to end it. |
| FR-56 | A disconnected player who returns (reopens the site, same session) before the grace period in FR-55 elapses can rejoin the same in-progress game and resume play from the current board state. |
| FR-57 | Cross-device games are two-participant only — no third party can join, observe cell-level live state, or be added to an in-progress or pending cross-device game (this is a hard boundary against accidental spectating; see Section 4 Out of Scope). |
| FR-58 | Cross-device human-vs-human is additive: v1's same-device human-vs-human mode (FR-9) remains available unchanged and is not removed or hidden behind the new mode. Mode selection (v1 FR-7) now offers three choices: vs AI, vs Human (same device), vs Human (invite/online). |
| FR-59 | A player cannot receive/accept a challenge while already in another in-progress cross-device game (prevents one profile from being in two live cross-device games simultaneously). Same-device and vs-AI games are unaffected by this restriction. |
| FR-60 | Refreshing the page during an in-progress cross-device game must **not** lose game state the way v1 FR-34 allows for local games — since the whole point is a persistent live session across two independent devices/browser instances, at minimum the current board/turn must be recoverable on reload (mechanism is the Architect's call; see Section 5 flag under Q2). |

### 3.3 UI/Visual Design Overhaul

| # | Requirement |
|---|-------------|
| FR-61 | All pages (home/mode-select, sign-in, game board, profile/stats, leaderboard, and the new challenge/invite screens from Section 3.2) share one consistent visual system: consistent color palette, typography (font family/sizing scale), spacing, and component styling (buttons, form fields, cards/panels) — no page should look like it was designed independently of the others. |
| FR-62 | The game board and turn indicator must make the following visually unambiguous at a glance, without reading text: whose turn it is, which mark is X vs O, which cells are filled vs empty, and — on game end — win vs. loss vs. tie, and (on a win) the winning line must be visually highlighted/distinguished from the rest of the board. |
| FR-63 | The site must be comfortably usable on a mobile-width viewport (e.g., ~375px wide) with no horizontal scrolling and no pinch-zoom required to read text or hit tap targets: this includes the game board, all forms (sign-in, profile creation, challenge), the leaderboard table, and the nav. This did not exist in v1 (only a viewport meta tag was present; no responsive layout rules) — v2 must actually deliver it, not just declare intent. |
| FR-64 | Interactive elements (buttons, links, form inputs, empty board cells) must have a visually distinct hover/focus state (for pointer/keyboard users) and disabled state (e.g., an already-filled cell, a submit button while a request is in flight) so the UI never appears to silently ignore input. |
| FR-65 | Error and validation states (e.g., wrong PIN, name taken, malformed input — per v1 FR-10/FR-21) must be visually distinct (not just plain text appended to the page) — e.g., clearly marked as an error near the relevant field, distinguishable at a glance from normal page content. |
| FR-66 | Loading/in-progress states that take a perceptible amount of time (e.g., a move being submitted, an AI reply being computed, a challenge being sent) must show a visible indicator rather than leaving the UI static with no feedback that the action registered. |
| FR-67 | The redesign must not alter any v1 functional behavior — this is a visual/UX pass on top of existing functionality (plus the new v2 features above), not a rules or flow change. Existing acceptance criteria from PRD v1 Section 6 must still pass unmodified. |
| FR-68 | "Done" for this initiative is defined as: FR-61–FR-66 verifiably met (testable per-requirement, e.g., FR-63 checked at a defined breakpoint, FR-62 checked by a reviewer without reading any text) — see Section 5 Q4 for how this gets signed off, since "looks good" alone isn't a testable acceptance criterion. |

---

## 4. Out of Scope for v2

Explicitly **not** being built, to prevent the real-time feature in particular from creeping into a much larger product:

- **Real authentication** (passwords, email/username login, OAuth/social login) — still out of scope; PIN recovery is a scoped, minimal exception (Section 5 Q1), not a step toward full auth.
- **Spectator mode** for cross-device games — v1 already excluded this for local games; it stays excluded for cross-device games too (FR-57). A third party cannot watch a live game in progress.
- **Matchmaking / random opponent queues / ranked play.** Cross-device play in v2 is invite-by-known-display-name only (FR-44) — no "find me an opponent" system. This is a judgment call: the stakeholder's request ("play against each other," "invite") reads as directed challenges between people who already know each other's profile name, not anonymous matchmaking, which is a materially larger feature (queueing, skill matching, abandonment penalties at scale).
- **In-game chat or messaging** between cross-device opponents — still out of scope, as in v1.
- **Tournament brackets** — still out of scope.
- **Friends lists / social graph / follow features** — still out of scope. Challenging is by typed display name each time, not a persistent friends list. (Flagged in Section 5 as a plausible fast-follow, not built now.)
- **Push notifications (mobile OS-level) or email/SMS alerts for challenges.** How an invitee learns of a challenge is addressed in-product only (Section 5 Q2) — no native app, no email infrastructure, no SMS.
- **Native mobile apps** — v2's mobile requirement (FR-63) is a responsive web layout, not an App Store/Play Store build, consistent with v1's stance.
- **Per-mode stat breakdowns** (e.g., splitting stats for cross-device vs. same-device human games) — cross-device human-vs-human results roll into the same "human" stats bucket as same-device (still no differentiation from v1 FR-27/Q7). Revisit only if the stakeholder asks.
- **A visual design system as a reusable/exported artifact** (e.g., a formal component library, Storybook, design tokens as a shipped package) — v2 needs the site itself to look and behave consistently (FR-61); it does not need a productized design system as a deliverable.
- **Full rebrand** (new name/logo/domain) — this is a visual consistency and polish pass on the existing product, not a rebrand.
- **Admin tooling to manage disconnected/abandoned cross-device games** — FR-55's resolution must be automatic; no admin dashboard to manually intervene in stuck games (matches v1's "no admin moderation tools" stance).

---

## 5. Open Questions / Recommendations

| # | Question | Recommendation |
|---|----------|-----------------|
| Q1 | **PIN recovery mechanism** — what's the actual recovery evidence (FR-38), given no email/real-auth infrastructure exists and adding one is explicitly not the goal? | Three options considered: **(a) security question(s)** set at profile creation (e.g., one free-text Q&A pair) — zero new infrastructure, but weak (guessable/forgettable, same "casual, not secure" tier as the PIN itself) and doesn't clearly beat just... remembering a PIN. **(b) A recovery code shown once at profile creation** (like a backup code) that the player is told to save somewhere safe — no infrastructure needed, stronger than a security question, but if the player didn't save it, they're in exactly the same locked-out state, and it's an unfamiliar pattern for a casual game. **(c) Email address, collected once at profile creation, used solely to send a one-time reset link/code.** **Recommended: (c), scoped narrowly, as a deliberate exception — not scope creep.** Reasoning: this is the only option that actually solves "I forgot everything and have no artifact saved" — which is the realistic failure mode the stakeholder is reacting to (a's security question is just a second thing to forget; b's backup code is just a second secret to lose). The scoped exception is narrow: email is used **only** to send a reset link/code — no email verification step at signup (don't block account creation on it), no email/password login path, no email shown/used anywhere else in the product, collection is **optional at profile creation but required to be present later in order to use recovery** (hence FR-42's "no recovery on file" case for anyone who skips it, including all pre-v2 profiles). This keeps "no real auth system" true while closing the actual gap. Flag for Architect: this requires *some* outbound email capability (e.g., a transactional email API/service), which is new infrastructure — small, but real, and worth sizing before committing. |
| Q2 | **How does the invited player learn about a cross-device challenge (FR-46)?** | Recommended default: **in-product only, polled/pushed while the invitee is on the site** — e.g., a visible "pending challenges" indicator that appears when they're signed in and viewing any page (nav badge), plus the pending challenge is listed and actionable from their own profile/home screen the next time they load or are already on the site. No email/SMS/push (see Section 4). Tradeoff being accepted explicitly: if the invitee isn't on the site at all, they won't know they've been challenged until they next visit — this is a real limitation, but adding an out-of-band notification channel is a materially bigger infrastructure ask than the stakeholder's request implies. If this limitation proves to make the feature feel broken in practice, revisit with the stakeholder before adding a notification channel. |
| Q3 | **Disconnect/abandonment handling (FR-55)** — auto-forfeit vs. abandon-unscored? | Recommended default: **grace period (suggest 2 minutes of no activity/heartbeat from the disconnected player) → auto-forfeit as a loss for the disconnected player, win for the connected one**, consistent with how a walkover is normally handled in casual online games, and it means stats still update meaningfully (an abandoned-unscored game would let a player dodge a loss just by closing the tab when losing, which invites bad behavior). Exact grace-period length is an Architect/tuning call; 2 minutes is a reasonable product default balancing "don't punish a brief phone-lock" against "don't leave a game open forever." |
| Q4 | **How is "done" on the UI overhaul (FR-68) actually signed off**, given "make it pretty" isn't testable? | Recommend a lightweight design review checklist gated on FR-61–FR-66 specifically (one pass/fail per requirement, e.g., "FR-63: verified at 375px width, no horizontal scroll, on pages X/Y/Z"), reviewed by the stakeholder + one other person before calling v2's UI work complete — not a subjective "stakeholder likes it now" bar alone, though the stakeholder's sign-off is still the final gate given they're the one who flagged this. |
| Q5 | **Should a cross-device challenge be revocable/discoverable by display name only, or does this leak information (e.g., confirms a name exists)?** | Recommend: challenging a nonexistent display name fails immediately with the same non-revealing-style error philosophy as v1's sign-in (don't distinguish "exists but declined" from other failure modes where practical), but note this is inherently a bit leakier than v1's sign-in flow, since a successful challenge send *does* confirm the name exists (there's no way to "challenge" a name that isn't real without some signal). Accept this as a minor, low-stakes leak (display names are already semi-public via the leaderboard) rather than engineering around it. |
| Q6 | **Friends list as a v2.1 fast-follow?** | Not recommending it for v2 (Section 4), but flagging: if cross-device play is well-received, "recently played with" or a lightweight favorites list to avoid retyping display names each time is a natural, small, low-risk next step. Not scoped now — mentioned only so it isn't rediscovered as a surprise later. |

---
