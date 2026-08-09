"""
GET/POST live-game endpoints (DESIGN_V2.md Section 2.3), incl. /current.
Disconnect detection & lazy auto-forfeit (Section 2.4). PRD_V2 U16/U17,
FR-50-57, FR-59-60.

Cross-device games are DB-backed (`live_games` table), unlike v1's
in-memory `active_games` -- see DESIGN_V2.md Section 2.3 for why (Render
free-tier idle timeouts, FR-60's reload-survival requirement). The poll
endpoint IS the heartbeat: every GET/POST touch updates the caller's own
*_last_seen_at, and checks the opponent's staleness before responding.

Authorization is real (FR-57): unlike v1's guest/local games (which rely
on game_id unguessability), every endpoint here checks the session
cookie's profile against x_profile_id/o_profile_id and 403s anyone else.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from app import auth, db, game as game_rules
from app.games_api import finalize_game_stats

router = APIRouter()

# Section 2.4 thresholds, derived from the 2s poll interval and PRD Q3's
# 2-minute grace-period recommendation.
CONNECTED_MAX_SECONDS = 20
GRACE_PERIOD_SECONDS = 120


def _iso_now() -> str:
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _seconds_since(iso_ts: str) -> float:
    """Both timestamps are produced by the same _iso_now()-style format
    (this module or SQLite's strftime default), so a plain parse is safe."""
    dt = datetime.strptime(iso_ts, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds()


def _signed_in_profile(request: Request) -> Optional[dict]:
    token = request.cookies.get(auth.COOKIE_NAME)
    return auth.get_profile_for_token(token)


def _get_game(game_id) -> Optional[dict]:
    return db.query_one_dict("SELECT * FROM live_games WHERE id = ?", (game_id,))


def _stats_result(status: str) -> str:
    """Map a live_games terminal status (which includes forfeits) onto
    the 'x_won'/'o_won'/'tie' vocabulary finalize_game_stats expects -- a
    forfeit is scored as a real win/loss for the connected/disconnected
    player (PRD Q3), not a distinct stats bucket."""
    return {
        "x_won": "x_won",
        "o_won": "o_won",
        "tie": "tie",
        "forfeited_x": "o_won",  # X forfeited -> O wins
        "forfeited_o": "x_won",  # O forfeited -> X wins
    }[status]


def _finalize_terminal_game(g: dict, status: str) -> None:
    """Stamp status/ended_at, then reuse the SAME game_results/stats
    logic v1's local human-vs-human already uses (games_api.py) --
    mode='human', difficulty=NULL, exactly as DESIGN_V2.md Section 2.3
    specifies ("no new stats code"). Cross-device results roll into the
    same stats bucket as local human games."""
    db.execute(
        "UPDATE live_games SET status = ?, ended_at = ? WHERE id = ?",
        (status, _iso_now(), g["id"]),
    )
    finalize_game_stats("human", None, g["x_profile_id"], g["o_profile_id"], _stats_result(status))


def _touch_and_check(g: dict, caller_mark: str) -> dict:
    """
    The heartbeat + lazy disconnect resolution (Section 2.4), run on
    every GET/POST touch of this game:
      1. Update the CALLER's own last_seen_at -- they just touched, so
         they can't be the stale one this request.
      2. Check only the OPPONENT's staleness. If the opponent has been
         idle past the 120s grace period, their mark forfeits right now,
         scored as a real loss/win via the normal stats path (PRD Q3).
    Returns the (possibly now-terminal) game row.
    """
    now = _iso_now()
    seen_column = "x_last_seen_at" if caller_mark == "X" else "o_last_seen_at"
    db.execute(f"UPDATE live_games SET {seen_column} = ? WHERE id = ?", (now, g["id"]))
    g = dict(g)
    g[seen_column] = now

    if g["status"] == "in_progress":
        opponent_column = "o_last_seen_at" if caller_mark == "X" else "x_last_seen_at"
        opponent_idle = _seconds_since(g[opponent_column])
        if opponent_idle > GRACE_PERIOD_SECONDS:
            forfeit_status = "forfeited_o" if caller_mark == "X" else "forfeited_x"
            _finalize_terminal_game(g, forfeit_status)
            g = _get_game(g["id"])

    return g


def _opponent_state(idle_seconds: float, status: str) -> str:
    if status != "in_progress":
        return "forfeited" if status.startswith("forfeited") else "connected"
    if idle_seconds < CONNECTED_MAX_SECONDS:
        return "connected"
    if idle_seconds <= GRACE_PERIOD_SECONDS:
        return "stale"
    return "forfeited"  # shouldn't normally be reached (touch already resolves it), safe fallback


def _public_view(g: dict, caller_mark: str) -> dict:
    winner_mark = {"x_won": "X", "o_won": "O"}.get(g["status"])
    line = game_rules.winning_line(list(g["board"])) if winner_mark else None
    opponent_column = "o_last_seen_at" if caller_mark == "X" else "x_last_seen_at"
    opponent_idle = _seconds_since(g[opponent_column])
    return {
        "game_id": g["id"],
        "board": g["board"],
        "current_turn": g["current_turn"],
        "status": g["status"],
        "winner": winner_mark,
        "winning_line": line,
        "opponent_state": _opponent_state(opponent_idle, g["status"]),
    }


def _authorize(g: dict, profile: dict):
    """Returns the caller's mark ('X'/'O') or None if not a participant."""
    if profile["id"] == g["x_profile_id"]:
        return "X"
    if profile["id"] == g["o_profile_id"]:
        return "O"
    return None


@router.get("/api/live-games/current")
async def get_current_live_game(request: Request):
    """Powers the 'resume game' affordance (FR-56). Registered before the
    /{game_id} route below matters only for readability here since FastAPI
    matches path operations in declared order and 'current' would
    otherwise need to not collide with an int path param -- kept as a
    separate, unambiguous path segment either way."""
    profile = _signed_in_profile(request)
    if profile is None:
        return JSONResponse({"error": "not_signed_in"}, status_code=401)

    row = db.query_one_dict(
        "SELECT id FROM live_games WHERE status = 'in_progress' AND (x_profile_id = ? OR o_profile_id = ?) "
        "ORDER BY created_at DESC LIMIT 1",
        (profile["id"], profile["id"]),
    )
    if row is None:
        return Response(status_code=204)
    return JSONResponse({"game_id": row["id"]}, status_code=200)


@router.get("/api/live-games/{game_id}")
async def get_live_game(game_id: int, request: Request):
    profile = _signed_in_profile(request)
    if profile is None:
        return JSONResponse({"error": "not_signed_in"}, status_code=401)

    g = _get_game(game_id)
    if g is None:
        return JSONResponse({"error": "not_found"}, status_code=404)

    caller_mark = _authorize(g, profile)
    if caller_mark is None:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    g = _touch_and_check(g, caller_mark)
    return JSONResponse(_public_view(g, caller_mark), status_code=200)


@router.post("/api/live-games/{game_id}/moves")
async def make_live_move(game_id: int, request: Request):
    profile = _signed_in_profile(request)
    if profile is None:
        return JSONResponse({"error": "not_signed_in"}, status_code=401)

    g = _get_game(game_id)
    if g is None:
        return JSONResponse({"error": "not_found"}, status_code=404)

    caller_mark = _authorize(g, profile)
    if caller_mark is None:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    # Staleness check FIRST (Section 2.3's note: a stale opponent
    # shouldn't be able to out-race a forfeit with a last-second move
    # after the grace period's already elapsed) -- this also serves as
    # the caller's own heartbeat touch.
    g = _touch_and_check(g, caller_mark)

    if g["status"] != "in_progress":
        return JSONResponse(
            {"error": "game_already_finished", **_public_view(g, caller_mark)}, status_code=409
        )

    if g["current_turn"] != caller_mark:
        return JSONResponse({"error": "not_your_turn"}, status_code=409)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=422)

    cell = body.get("cell")
    board = list(g["board"])
    cell_is_valid_int = isinstance(cell, int) and not isinstance(cell, bool)
    if not game_rules.is_legal_move(board, cell if cell_is_valid_int else -1):
        return JSONResponse({"error": "illegal_move"}, status_code=400)

    board = game_rules.apply_move(board, cell, caller_mark)
    new_board_str = "".join(board)
    next_turn = game_rules.other_mark(caller_mark)

    db.execute(
        "UPDATE live_games SET board = ?, current_turn = ? WHERE id = ?",
        (new_board_str, next_turn, game_id),
    )
    g = _get_game(game_id)

    status = game_rules.game_status(board)
    if status != "in_progress":
        _finalize_terminal_game(g, status)
        g = _get_game(game_id)

    return JSONResponse(_public_view(g, caller_mark), status_code=200)
