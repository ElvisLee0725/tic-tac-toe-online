"""
POST /api/session (sign in), POST /api/session/new (create account),
GET /api/session, DELETE /api/session. (DESIGN.md Section 4.1.)

2026-08-06 revision: "Create Account" and "Sign In" are two distinct
actions/endpoints, not a single combined create-or-signin form -- see
PRD FR-18/FR-19 (revised 2026-08-06) for the rationale (an unrecognized
name used to silently create a throwaway account, which was a bug).
"""

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app import auth

router = APIRouter()


def _set_session_cookie(resp: JSONResponse, profile_id: int) -> JSONResponse:
    token = auth.create_session(profile_id)
    resp.set_cookie(
        key=auth.COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=True,
        max_age=auth.COOKIE_MAX_AGE,
        path="/",
    )
    return resp


def _parse_credentials(body: dict):
    """Returns (display_name, pin) or raises auth.ValidationError."""
    display_name = auth.validate_display_name(body.get("display_name"))
    pin = auth.validate_pin(body.get("pin"))
    return display_name, pin


@router.post("/api/session/new")
async def post_session_new(request: Request):
    """Create Account (FR-18). Fails with 409 name_taken if the name is
    already in use -- never signs the caller into the existing account.

    recovery_email is optional (v2, FR-38/PRD_V2 Q1) -- used solely to
    enable PIN recovery later; never required to create a profile."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=422)

    try:
        display_name, pin = _parse_credentials(body)
        recovery_email = auth.validate_recovery_email(body.get("recovery_email"))
    except auth.ValidationError as e:
        return JSONResponse({"error": "validation_error", "message": str(e)}, status_code=422)

    try:
        profile = auth.create_profile_explicit(display_name, pin, recovery_email)
    except auth.NameTakenError:
        return JSONResponse(
            {
                "error": "name_taken",
                "message": "That name is already taken -- sign in instead or choose another name.",
            },
            status_code=409,
        )

    resp = JSONResponse({"profile": auth.profile_to_dict(profile)}, status_code=201)
    return _set_session_cookie(resp, profile["id"])


@router.post("/api/session")
async def post_session(request: Request):
    """Sign In (FR-19). Fails with a single generic 401 whether the name
    doesn't exist or the PIN is wrong -- never creates an account."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=422)

    try:
        display_name, pin = _parse_credentials(body)
    except auth.ValidationError as e:
        return JSONResponse({"error": "validation_error", "message": str(e)}, status_code=422)

    try:
        profile = auth.sign_in(display_name, pin)
    except auth.SignInFailedError:
        return JSONResponse(
            {"error": "sign_in_failed", "message": "That username and PIN aren't recognized."},
            status_code=401,
        )

    resp = JSONResponse({"profile": auth.profile_to_dict(profile)}, status_code=200)
    return _set_session_cookie(resp, profile["id"])


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
