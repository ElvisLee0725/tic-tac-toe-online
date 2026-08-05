"""
Jinja2 page routes (DESIGN.md Section 8).
"""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app import auth, leaderboard_api

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
