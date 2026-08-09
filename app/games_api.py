"""
POST /api/games, POST /api/games/{id}/moves (DESIGN.md Section 4.2).

Both mode="ai" (Easy/Medium/Hard, server-computed AI reply within the
move endpoint) and mode="human" (local same-device human-vs-human,
FR-9/FR-10) are supported.

In-progress game state lives in the in-memory `active_games` dict,
keyed by a random UUIDv4 game_id, per DESIGN.md Section 1/4 -- this is
explicitly allowed to be lost on process restart (FR-34).
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import ai, auth, db, game as game_rules

router = APIRouter()

# game_id -> dict(board, mode, difficulty, current_turn, status,
#                  x_profile_id, o_profile_id, x_display_name, o_display_name)
active_games = {}


def _game_public_view(g: dict) -> dict:
    return {
        "game_id": g["game_id"],
        "mode": g["mode"],
        "difficulty": g["difficulty"],
        "board": "".join(g["board"]),
        "current_turn": g["current_turn"],
        "status": g["status"],
        "x": {"display_name": g["x_display_name"]},
        "o": {"display_name": g["o_display_name"]},
    }


def _signed_in_profile(request: Request) -> Optional[dict]:
    token = request.cookies.get(auth.COOKIE_NAME)
    return auth.get_profile_for_token(token)


@router.post("/api/games")
async def create_game(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    mode = body.get("mode")

    if mode == "ai":
        return await _create_ai_game(request, body)
    if mode == "human":
        return await _create_human_game(request, body)

    return JSONResponse(
        {"error": "unsupported_mode", "message": "mode must be 'ai' or 'human'."},
        status_code=400,
    )


async def _create_ai_game(request: Request, body: dict):
    difficulty = body.get("difficulty")
    guest_requested = bool(body.get("guest", False))

    if not isinstance(difficulty, str) or difficulty not in ai.SUPPORTED_DIFFICULTIES:
        return JSONResponse(
            {
                "error": "unsupported_difficulty",
                "message": "difficulty must be one of: easy, medium, hard.",
            },
            status_code=400,
        )

    # Guest-ness is determined server-side, never trusted from the client
    # alone: a valid session cookie always wins over a client-supplied
    # guest:true, so a signed-in player can't dodge stat recording by
    # just adding guest:true to the request body (QA Finding #3). Only
    # when there's genuinely no valid session is guest:true honored.
    x_profile_id = None
    x_display_name = "Guest"
    profile = _signed_in_profile(request)
    if profile is not None:
        x_profile_id = profile["id"]
        x_display_name = profile["display_name"]
    elif not guest_requested:
        return JSONResponse({"error": "not_signed_in"}, status_code=401)

    game_id = str(uuid.uuid4())
    g = {
        "game_id": game_id,
        "mode": "ai",
        "difficulty": difficulty,
        "board": game_rules.new_board(),
        "current_turn": "X",
        "status": "in_progress",
        "x_profile_id": x_profile_id,
        "o_profile_id": None,
        "x_display_name": x_display_name,
        "o_display_name": f"AI ({difficulty.capitalize()})",
    }
    active_games[game_id] = g
    return JSONResponse(_game_public_view(g), status_code=201)


async def _create_human_game(request: Request, body: dict):
    """
    vs Human (local), FR-9/FR-10. The device owner (X) must already be
    signed in; the second local player (O) is identified by
    opponent_name/opponent_pin in the request body, verified with
    auth.sign_in() -- the same sign-in-only logic POST /api/session uses
    (2026-08-06 revision). O must already have an existing account; this
    deliberately does NOT silently create one for them (a second local
    player shouldn't be auto-registered without a moment where they
    intentionally set up their own profile -- see FR-18/19). This does
    NOT touch the browser's own session/cookie, X stays signed in
    throughout.
    """
    x_profile = _signed_in_profile(request)
    if x_profile is None:
        return JSONResponse({"error": "not_signed_in"}, status_code=401)

    try:
        opponent_name = auth.validate_display_name(body.get("opponent_name"))
        opponent_pin = auth.validate_pin(body.get("opponent_pin"))
    except auth.ValidationError as e:
        return JSONResponse({"error": "validation_error", "message": str(e)}, status_code=422)

    try:
        o_profile = auth.sign_in(opponent_name, opponent_pin)
    except auth.SignInFailedError:
        return JSONResponse({"error": "opponent_signin_failed"}, status_code=401)

    if o_profile["id"] == x_profile["id"]:
        return JSONResponse(
            {"error": "cannot_play_self", "message": "The second player must be a different profile."},
            status_code=400,
        )

    game_id = str(uuid.uuid4())
    g = {
        "game_id": game_id,
        "mode": "human",
        "difficulty": None,
        "board": game_rules.new_board(),
        "current_turn": "X",
        "status": "in_progress",
        "x_profile_id": x_profile["id"],
        "o_profile_id": o_profile["id"],
        "x_display_name": x_profile["display_name"],
        "o_display_name": o_profile["display_name"],
    }
    active_games[game_id] = g
    return JSONResponse(_game_public_view(g), status_code=201)


def finalize_game_stats(mode: str, difficulty, x_profile_id: int, o_profile_id, status: str) -> dict:
    """
    Shared stats-finalization logic: insert the game_results audit row and
    increment wins/losses/ties for every real participant. Used by both
    v1's local games (_finalize_if_terminal below) and v2's cross-device
    live_games (live_games_api.py) on terminal state -- one implementation,
    per PRD Q8 / DESIGN_V2.md Section 2.3 ("no new stats code, reuse what
    exists"). x_profile_id must be non-None (guest AI games never call
    this at all). o_profile_id is None for vs-AI games (the AI has no
    profile/stats) and a real profile id for any human opponent.
    """
    result = {"x_won": "x_won", "o_won": "o_won", "tie": "tie"}[status]
    db.execute(
        """INSERT INTO game_results (mode, difficulty, x_profile_id, o_profile_id, result)
           VALUES (?, ?, ?, ?, ?)""",
        (mode, difficulty, x_profile_id, o_profile_id, result),
    )

    def _bump(profile_id: int, column: str):
        db.execute(f"UPDATE profiles SET {column} = {column} + 1 WHERE id = ?", (profile_id,))

    if status == "tie":
        _bump(x_profile_id, "ties")
    elif status == "x_won":
        _bump(x_profile_id, "wins")
    else:  # o_won
        _bump(x_profile_id, "losses")

    profile_updates = {"x": auth.profile_to_dict(auth.get_profile_by_id(x_profile_id))}

    if o_profile_id is not None:
        if status == "tie":
            _bump(o_profile_id, "ties")
        elif status == "o_won":
            _bump(o_profile_id, "wins")
        else:  # x_won
            _bump(o_profile_id, "losses")
        profile_updates["o"] = auth.profile_to_dict(auth.get_profile_by_id(o_profile_id))

    return profile_updates


def _finalize_if_terminal(g: dict) -> Optional[dict]:
    """If the game just reached a terminal state, finalize stats (skipped
    entirely for guest games, where x_profile_id is None), and drop the
    game from active_games. Returns a profile_updates dict or None."""
    status = game_rules.game_status(g["board"])
    g["status"] = status
    if status == "in_progress":
        return None

    profile_updates = None
    if g["x_profile_id"] is not None:
        profile_updates = finalize_game_stats(
            g["mode"], g["difficulty"], g["x_profile_id"], g["o_profile_id"], status
        )

    # Note: the finished game is deliberately left in active_games (not
    # popped) so the "already finished" check in make_move() below can
    # actually return 409 game_already_finished instead of 404 not_found
    # (QA Finding #2). This is consistent with Finding #6 (accepted,
    # informational-only): active_games already grows unbounded for
    # abandoned in-progress games, so leaving finished games in place too
    # doesn't introduce a new class of problem.
    return profile_updates


@router.post("/api/games/{game_id}/moves")
async def make_move(game_id: str, request: Request):
    g = active_games.get(game_id)
    if g is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if g["status"] != "in_progress":
        return JSONResponse({"error": "game_already_finished"}, status_code=409)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=422)

    cell = body.get("cell")
    mover_mark = g["current_turn"]
    cell_is_valid_int = isinstance(cell, int) and not isinstance(cell, bool)
    if not game_rules.is_legal_move(g["board"], cell if cell_is_valid_int else -1):
        return JSONResponse({"error": "illegal_move"}, status_code=400)

    g["board"] = game_rules.apply_move(g["board"], cell, mover_mark)
    ai_move_info = None
    profile_updates = _finalize_if_terminal(g)

    if g["status"] == "in_progress":
        g["current_turn"] = game_rules.other_mark(mover_mark)

        if g["mode"] == "ai" and g["current_turn"] == "O":
            ai_cell = ai.select_move(g["board"], "O", g["difficulty"])
            g["board"] = game_rules.apply_move(g["board"], ai_cell, "O")
            ai_move_info = {"cell": ai_cell}
            profile_updates = _finalize_if_terminal(g)
            if g["status"] == "in_progress":
                g["current_turn"] = "X"
        # mode == "human": no auto-response, it's the other local
        # player's turn on the same screen -- just leave current_turn
        # flipped and return.

    status = g["status"]
    winner_mark = {"x_won": "X", "o_won": "O"}.get(status)

    resp = {
        "game_id": game_id,
        "board": "".join(g["board"]),
        "current_turn": g["current_turn"],
        "status": status,
        "winner": winner_mark,
        "ai_move": ai_move_info,
    }
    if profile_updates is not None:
        resp["profile_updates"] = profile_updates
    return JSONResponse(resp, status_code=200)
