"""
Jinja2 page routes (DESIGN.md Section 8).

Scope note: only home, sign-in, and game pages are built for today's
U1+U2 slice. profile.html / leaderboard.html are deferred.
"""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app import auth

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
