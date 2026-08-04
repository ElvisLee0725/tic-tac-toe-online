"""
POST/GET /api/session (DESIGN.md Section 4.1).

Scope note: DELETE /api/session (sign out) is skipped for today's
U1+U2 slice per current direction; auth.delete_session() already exists
in auth.py so wiring it up later is a two-line addition.
"""

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app import auth

router = APIRouter()


@router.post("/api/session")
async def post_session(request: Request, response: Response):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=422)

    try:
        display_name = auth.validate_display_name(body.get("display_name"))
        pin = auth.validate_pin(body.get("pin"))
    except auth.ValidationError as e:
        return JSONResponse({"error": "validation_error", "message": str(e)}, status_code=422)

    try:
        profile = auth.create_or_signin(display_name, pin)
    except auth.WrongPinError:
        return JSONResponse({"error": "wrong_pin"}, status_code=401)

    token = auth.create_session(profile["id"])
    resp = JSONResponse({"profile": auth.profile_to_dict(profile)}, status_code=200)
    resp.set_cookie(
        key=auth.COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=auth.COOKIE_MAX_AGE,
        path="/",
    )
    return resp


@router.get("/api/session")
async def get_session(request: Request):
    token = request.cookies.get(auth.COOKIE_NAME)
    profile = auth.get_profile_for_token(token)
    if profile is None:
        return JSONResponse({"error": "not_signed_in"}, status_code=401)
    return JSONResponse({"profile": auth.profile_to_dict(profile)}, status_code=200)


@router.delete("/api/session")
async def delete_session(request: Request):
    token = request.cookies.get(auth.COOKIE_NAME)
    if token:
        auth.delete_session(token)
    resp = Response(status_code=204)
    resp.delete_cookie(key=auth.COOKIE_NAME, path="/")
    return resp
