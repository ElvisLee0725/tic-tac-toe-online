"""
Jinja2 page routes (DESIGN.md Section 8).
"""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app import auth, db, leaderboard_api

router = APIRouter()

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


def _current_profile(request: Request):
    token = request.cookies.get(auth.COOKIE_NAME)
    return auth.get_profile_for_token(token)


@router.get("/")
async def index(request: Request):
    profile = _current_profile(request)
    return templates.TemplateResponse(
        request, "index.html", {"profile": profile}
    )


@router.get("/signin")
async def signin(request: Request):
    profile = _current_profile(request)
    return templates.TemplateResponse(
        request, "signin.html", {"profile": profile}
    )


@router.get("/game")
async def game_page(request: Request):
    profile = _current_profile(request)
    return templates.TemplateResponse(
        request, "game.html", {"profile": profile}
    )


@router.get("/profile")
async def profile_page(request: Request):
    profile = _current_profile(request)
    if profile is None:
        return RedirectResponse(url="/signin", status_code=302)
    return templates.TemplateResponse(
        request, "profile.html", {"profile": profile}
    )


@router.get("/leaderboard")
async def leaderboard_page(request: Request):
    profile = _current_profile(request)
    data = leaderboard_api.compute_leaderboard(request)
    return templates.TemplateResponse(
        request,
        "leaderboard.html",
        {"profile": profile, "top": data["top"], "me": data["me"]},
    )


@router.get("/forgot-pin")
async def forgot_pin_page(request: Request):
    """PIN recovery request form (FR-37, DESIGN_V2.md Section 1)."""
    profile = _current_profile(request)
    return templates.TemplateResponse(
        request, "forgot_pin.html", {"profile": profile}
    )


@router.get("/challenges")
async def challenges_page(request: Request):
    """Incoming/outgoing pending challenges (FR-44-49, DESIGN_V2.md
    Section 2.2.1). Also feeds the nav badge (challenges.js)."""
    profile = _current_profile(request)
    if profile is None:
        return RedirectResponse(url="/signin", status_code=302)
    return templates.TemplateResponse(
        request, "challenges.html", {"profile": profile}
    )


@router.get("/play/live/{game_id}")
async def live_game_page(game_id: int, request: Request):
    """
    Cross-device game board (DESIGN_V2.md Section 2.3). live-board.js
    does the polling; this route's only job is auth + handing the page
    the identity context (my mark, both display names) that the poll
    endpoint's response shape deliberately doesn't carry (Section 2.3's
    response is board/turn/status/winner/winning_line/opponent_state
    only), so board.js/live-board.js don't need a second identity call.
    """
    profile = _current_profile(request)
    if profile is None:
        return RedirectResponse(url="/signin", status_code=302)

    game_row = db.query_one_dict("SELECT * FROM live_games WHERE id = ?", (game_id,))
    if game_row is None or profile["id"] not in (game_row["x_profile_id"], game_row["o_profile_id"]):
        return RedirectResponse(url="/challenges", status_code=302)

    x_profile = auth.get_profile_by_id(game_row["x_profile_id"])
    o_profile = auth.get_profile_by_id(game_row["o_profile_id"])
    my_mark = "X" if profile["id"] == game_row["x_profile_id"] else "O"

    return templates.TemplateResponse(
        request,
        "live_game.html",
        {
            "profile": profile,
            "game_id": game_id,
            "my_mark": my_mark,
            "x_name": x_profile["display_name"],
            "o_name": o_profile["display_name"],
        },
    )


@router.get("/reset-pin")
async def reset_pin_page(request: Request):
    """
    Landed on via the emailed reset link. Token validity is checked
    server-side before rendering, per DESIGN_V2.md Section 1.4 -- an
    invalid/expired/used/missing token shows a plain error instead of the
    new-PIN form.
    """
    profile = _current_profile(request)
    token = request.query_params.get("token")
    token_valid = auth.get_valid_pin_reset(token) is not None
    return templates.TemplateResponse(
        request,
        "reset_pin.html",
        {"profile": profile, "token": token, "token_valid": token_valid},
    )
