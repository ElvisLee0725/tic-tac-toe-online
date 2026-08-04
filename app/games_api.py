"""
POST /api/games, POST /api/games/{id}/moves (DESIGN.md Section 4.2).

Scope note (today's slice): only mode="ai", difficulty="easy" is wired
up end to end. mode="human" and difficulty in {"medium","hard"} are
rejected with a clear 400 rather than silently accepted -- deferred to
a later slice, not forgotten.

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
    difficulty = body.get("difficulty")
    guest = bool(body.get("guest", False))

    if mode != "ai":
        return JSONResponse(
            {"error": "unsupported_mode", "message": "Only mode='ai' is supported right now."},
            status_code=400,
        )
    if difficulty != "easy":
        return JSONResponse(
            {
                "error": "unsupported_difficulty",
                "message": "Only difficulty='easy' is supported right now (medium/hard coming soon).",
            },
            status_code=400,
        )

    x_profile_id = None
    x_display_name = "Guest"
    if not guest:
        profile = _signed_in_profile(request)
        if profile is None:
            return JSONResponse({"error": "not_signed_in"}, status_code=401)
        x_profile_id = profile["id"]
        x_display_name = profile["display_name"]

    game_id = str(uuid.uuid4())
    g = {
        "game_id": game_id,
        "mode": mode,
        "difficulty": difficulty,
        "board": game_rules.new_board(),
        "current_turn": "X",
        "status": "in_progress",
        "x_profile_id": x_profile_id,
        "o_profile_id": None,
        "x_display_name": x_display_name,
        "o_display_name": "AI (Easy)",
    }
    active_games[game_id] = g
    return JSONResponse(_game_public_view(g), status_code=201)


def _finalize_if_terminal(g: dict) -> Optional[dict]:
    """If the game just reached a terminal state, write the audit log +
    increment profile counters (skipped for guest games), and drop the
    game from active_games. Returns profile_updates dict or None."""
    status = game_rules.game_status(g["board"])
    g["status"] = status
    if status == "in_progress":
        return None

    profile_updates = None
    if g["x_profile_id"] is not None:
        result = {"x_won": "x_won", "o_won": "o_won", "tie": "tie"}[status]
        db.execute(
            """INSERT INTO game_results (mode, difficulty, x_profile_id, o_profile_id, result)
               VALUES (?, ?, ?, ?, ?)""",
            (g["mode"], g["difficulty"], g["x_profile_id"], g["o_profile_id"], result),
        )
        if status == "tie":
            db.execute("UPDATE profiles SET ties = ties + 1 WHERE id = ?", (g["x_profile_id"],))
        elif status == "x_won":
            db.execute("UPDATE profiles SET wins = wins + 1 WHERE id = ?", (g["x_profile_id"],))
        else:  # o_won -- AI beat the human (won't happen on Easy in practice, but handled)
            db.execute("UPDATE profiles SET losses = losses + 1 WHERE id = ?", (g["x_profile_id"],))
        updated = auth.get_profile_by_id(g["x_profile_id"])
        profile_updates = {"x": auth.profile_to_dict(updated)}

    active_games.pop(g["game_id"], None)
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
    if g["current_turn"] != "X":
        return JSONResponse({"error": "not_your_turn"}, status_code=409)
    if not game_rules.is_legal_move(g["board"], cell if isinstance(cell, int) else -1):
        return JSONResponse({"error": "illegal_move"}, status_code=400)

    g["board"] = game_rules.apply_move(g["board"], cell, "X")
    ai_move_info = None
    profile_updates = _finalize_if_terminal(g)

    if g["status"] == "in_progress":
        g["current_turn"] = "O"
        ai_cell = ai.select_move(g["board"], "O", g["difficulty"])
        g["board"] = game_rules.apply_move(g["board"], ai_cell, "O")
        ai_move_info = {"cell": ai_cell}
        profile_updates = _finalize_if_terminal(g)
        if g["status"] == "in_progress":
            g["current_turn"] = "X"

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
