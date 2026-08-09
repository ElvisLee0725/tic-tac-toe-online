"""
POST /api/pin-recovery/request, POST /api/pin-recovery/reset.
(DESIGN_V2.md Section 1.4.)

The 5-case logic in _handle_recovery_request() is the important,
easy-to-get-wrong part: cases 1, 3, 4, 5 must all return the identical
generic response; only case 2 ("not_configured") is allowed to differ
(resolving the FR-42/FR-43 tension per DESIGN_V2.md Section 1.1).
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import auth, email

router = APIRouter()

GENERIC_RESPONSE = {
    "status": "sent_if_eligible",
    "message": "If that matches an account with recovery configured, we've emailed a reset link.",
}
NOT_CONFIGURED_RESPONSE = {
    "status": "not_configured",
    "message": (
        "This profile doesn't have PIN recovery set up. If this is your profile, "
        "you'll need to create a new one."
    ),
}


def _handle_recovery_request(display_name, submitted_email) -> dict:
    # Defensive against non-string JSON types (same class of bug fixed
    # elsewhere per QA Finding #1) -- just fall through to the generic
    # "nothing happened" response rather than crashing or leaking
    # anything by the shape of the error.
    if not isinstance(display_name, str) or not display_name.strip():
        return GENERIC_RESPONSE
    if not isinstance(submitted_email, str) or not submitted_email.strip():
        return GENERIC_RESPONSE

    # Case 1: name not found.
    profile = auth.get_profile_by_name(display_name.strip())
    if profile is None:
        return GENERIC_RESPONSE

    # Case 2: found, but no recovery configured -- the one case allowed
    # to be distinguishable (FR-42).
    if not profile.get("recovery_email"):
        return NOT_CONFIGURED_RESPONSE

    # Case 3: found, recovery configured, but submitted email doesn't match.
    if not auth.recovery_email_matches(profile, submitted_email):
        return GENERIC_RESPONSE

    # Case 5: found, email matches, but the 60s cooldown is active --
    # silently skip the send, same generic response as everything else.
    if auth.is_recovery_cooldown_active(profile["id"]):
        return GENERIC_RESPONSE

    # Case 4: the only case that actually sends anything. Response is
    # still worded/shaped identically to cases 1/3/5.
    token = auth.create_pin_reset_token(profile["id"])
    email.send_pin_reset_email(profile, token)
    return GENERIC_RESPONSE


@router.post("/api/pin-recovery/request")
async def post_pin_recovery_request(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    result = _handle_recovery_request(body.get("display_name"), body.get("email"))
    return JSONResponse(result, status_code=200)


@router.post("/api/pin-recovery/reset")
async def post_pin_recovery_reset(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=422)

    token = body.get("token")

    try:
        new_pin = auth.validate_pin(body.get("new_pin"))
    except auth.ValidationError as e:
        return JSONResponse({"error": "validation_error", "message": str(e)}, status_code=422)

    try:
        auth.reset_pin_with_token(token, new_pin)
    except auth.InvalidResetTokenError:
        return JSONResponse({"error": "invalid_or_expired_token"}, status_code=400)

    return JSONResponse({"ok": True}, status_code=200)
