"""
POST/GET/accept/decline/cancel challenge endpoints. (DESIGN_V2.md Section 2.2.)
PRD_V2 U14/U15/U18, FR-44-49.

accept_challenge() creates the actual live_games row (Section 2.3) once a
challenge is accepted -- see live_games_api.py for the cross-device game
itself (polling, moves, disconnect/forfeit).
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app import auth, db

router = APIRouter()

# Architect default (DESIGN_V2.md Section 2.2, Open Item V1) -- no concrete
# number was given in PRD_V2 Section 5 despite the FR-48 cross-reference.
CHALLENGE_EXPIRY_SECONDS = 5 * 60


def _iso_now() -> str:
    """Same ISO-8601-with-milliseconds format as SQLite's own
    strftime('%Y-%m-%dT%H:%M:%fZ','now'), so Python- and DB-computed
    timestamps compare correctly as plain strings (same pattern as
    auth.py's PIN-recovery helpers)."""
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _iso_plus_seconds(seconds: int) -> str:
    dt = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _signed_in_profile(request: Request) -> Optional[dict]:
    token = request.cookies.get(auth.COOKIE_NAME)
    return auth.get_profile_for_token(token)


def _lazily_expire(row: dict) -> dict:
    """Lazy, on-touch expiry (Section 2.2: no scheduler). Any read/
    accept/decline/cancel of a challenge past expires_at flips it to
    'expired' first. Also what frees up the pending-pair unique index
    for a fresh challenge between the same two people."""
    if row["status"] == "pending" and row["expires_at"] < _iso_now():
        db.execute("UPDATE challenges SET status = 'expired' WHERE id = ?", (row["id"],))
        row = dict(row)
        row["status"] = "expired"
    return row


def _get_challenge(challenge_id) -> Optional[dict]:
    row = db.query_one_dict("SELECT * FROM challenges WHERE id = ?", (challenge_id,))
    if row is None:
        return None
    return _lazily_expire(row)


def _create_or_refresh_challenge(challenger_id: int, invitee_id: int) -> dict:
    """
    FR-49 ("replaces, not stacked"): a new challenge from the same
    challenger to the same invitee while one is already pending updates
    the existing row's created_at/expires_at (resets the clock) instead
    of erroring or inserting a second row.
    """
    existing = db.query_one_dict(
        "SELECT * FROM challenges WHERE challenger_id = ? AND invitee_id = ? AND status = 'pending'",
        (challenger_id, invitee_id),
    )
    now = _iso_now()
    expires_at = _iso_plus_seconds(CHALLENGE_EXPIRY_SECONDS)

    if existing is not None:
        db.execute(
            "UPDATE challenges SET created_at = ?, expires_at = ? WHERE id = ?",
            (now, expires_at, existing["id"]),
        )
        return db.query_one_dict("SELECT * FROM challenges WHERE id = ?", (existing["id"],))

    cur = db.execute(
        "INSERT INTO challenges (challenger_id, invitee_id, status, created_at, expires_at) "
        "VALUES (?, ?, 'pending', ?, ?)",
        (challenger_id, invitee_id, now, expires_at),
    )
    return db.query_one_dict("SELECT * FROM challenges WHERE id = ?", (cur.lastrowid,))


def _invalid_invitee_response() -> JSONResponse:
    """
    Generic, non-revealing failure for both 'invitee doesn't exist' and
    'invitee is yourself' (PRD_V2 Q5's accepted minor leak -- a
    *successful* send does confirm the name exists, same as v1's
    leaderboard names being semi-public, but a *failed* send doesn't
    distinguish which failure case it was, mirroring v1 FR-19's
    philosophy where practical).
    """
    return JSONResponse(
        {"error": "invalid_invitee", "message": "Could not send a challenge to that name."},
        status_code=400,
    )


@router.post("/api/challenges")
async def create_challenge(request: Request):
    profile = _signed_in_profile(request)
    if profile is None:
        return JSONResponse({"error": "not_signed_in"}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        body = {}

    invitee_name = body.get("invitee_name")
    if not isinstance(invitee_name, str) or not invitee_name.strip():
        return _invalid_invitee_response()

    invitee = auth.get_profile_by_name(invitee_name.strip())
    if invitee is None or invitee["id"] == profile["id"]:
        return _invalid_invitee_response()

    challenge = _create_or_refresh_challenge(profile["id"], invitee["id"])
    return JSONResponse(
        {
            "challenge_id": challenge["id"],
            "invitee_name": invitee["display_name"],
            "status": challenge["status"],
            "expires_at": challenge["expires_at"],
        },
        status_code=201,
    )


@router.get("/api/challenges")
async def list_challenges(request: Request):
    profile = _signed_in_profile(request)
    if profile is None:
        return JSONResponse({"error": "not_signed_in"}, status_code=401)

    incoming_rows = db.query_dicts(
        """SELECT c.*, p.display_name AS other_name
           FROM challenges c JOIN profiles p ON p.id = c.challenger_id
           WHERE c.invitee_id = ? AND c.status = 'pending'
           ORDER BY c.created_at DESC""",
        (profile["id"],),
    )
    outgoing_rows = db.query_dicts(
        """SELECT c.*, p.display_name AS other_name
           FROM challenges c JOIN profiles p ON p.id = c.invitee_id
           WHERE c.challenger_id = ? AND c.status = 'pending'
           ORDER BY c.created_at DESC""",
        (profile["id"],),
    )

    incoming = []
    for row in incoming_rows:
        row = _lazily_expire(row)
        if row["status"] != "pending":
            continue
        incoming.append(
            {
                "challenge_id": row["id"],
                "challenger_name": row["other_name"],
                "status": row["status"],
                "created_at": row["created_at"],
                "expires_at": row["expires_at"],
            }
        )

    outgoing = []
    for row in outgoing_rows:
        row = _lazily_expire(row)
        if row["status"] != "pending":
            continue
        outgoing.append(
            {
                "challenge_id": row["id"],
                "invitee_name": row["other_name"],
                "status": row["status"],
                "created_at": row["created_at"],
                "expires_at": row["expires_at"],
            }
        )

    return JSONResponse({"incoming": incoming, "outgoing": outgoing}, status_code=200)


@router.post("/api/challenges/{challenge_id}/accept")
async def accept_challenge(challenge_id: int, request: Request):
    profile = _signed_in_profile(request)
    if profile is None:
        return JSONResponse({"error": "not_signed_in"}, status_code=401)

    challenge = _get_challenge(challenge_id)
    if challenge is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if challenge["invitee_id"] != profile["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    if challenge["status"] != "pending":
        return JSONResponse(
            {"error": "challenge_not_pending", "status": challenge["status"]}, status_code=409
        )

    # FR-59: can't accept while already in another in-progress live game.
    already_in_game = db.query_one_dict(
        "SELECT id FROM live_games WHERE status = 'in_progress' AND (x_profile_id = ? OR o_profile_id = ?)",
        (profile["id"], profile["id"]),
    )
    if already_in_game is not None:
        return JSONResponse({"error": "already_in_live_game"}, status_code=409)

    # Create the live_games row (FR-52: challenger is X and moves first,
    # the accepting player is O) and link it back onto the challenge.
    cur = db.execute(
        "INSERT INTO live_games (x_profile_id, o_profile_id) VALUES (?, ?)",
        (challenge["challenger_id"], profile["id"]),
    )
    game_id = cur.lastrowid
    db.execute(
        "UPDATE challenges SET status = 'accepted', game_id = ? WHERE id = ?",
        (game_id, challenge_id),
    )
    return JSONResponse(
        {"challenge_id": challenge_id, "status": "accepted", "game_id": game_id}, status_code=201
    )


@router.post("/api/challenges/{challenge_id}/decline")
async def decline_challenge(challenge_id: int, request: Request):
    profile = _signed_in_profile(request)
    if profile is None:
        return JSONResponse({"error": "not_signed_in"}, status_code=401)

    challenge = _get_challenge(challenge_id)
    if challenge is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if challenge["invitee_id"] != profile["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    if challenge["status"] != "pending":
        return JSONResponse(
            {"error": "challenge_not_pending", "status": challenge["status"]}, status_code=409
        )

    db.execute("UPDATE challenges SET status = 'declined' WHERE id = ?", (challenge_id,))
    return Response(status_code=204)


@router.delete("/api/challenges/{challenge_id}")
async def cancel_challenge(challenge_id: int, request: Request):
    profile = _signed_in_profile(request)
    if profile is None:
        return JSONResponse({"error": "not_signed_in"}, status_code=401)

    challenge = _get_challenge(challenge_id)
    if challenge is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if challenge["challenger_id"] != profile["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    if challenge["status"] != "pending":
        return JSONResponse(
            {"error": "challenge_not_pending", "status": challenge["status"]}, status_code=409
        )

    db.execute("UPDATE challenges SET status = 'cancelled' WHERE id = ?", (challenge_id,))
    return Response(status_code=204)
