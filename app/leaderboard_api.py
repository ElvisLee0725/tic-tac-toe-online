"""
GET /api/leaderboard (DESIGN.md Section 3.3, Section 4.3, FR-28-33).
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import auth, db

router = APIRouter()

TOP_SQL = """
    SELECT id, display_name, wins, losses, ties, (wins - losses) AS score, created_at
    FROM profiles
    WHERE (wins + losses + ties) >= 5
    ORDER BY score DESC, wins DESC, created_at ASC
    LIMIT 10
"""

MY_RANK_SQL = """
    SELECT COUNT(*) + 1 AS my_rank
    FROM profiles
    WHERE (wins + losses + ties) >= 5
      AND (
            (wins - losses) > ?
         OR ((wins - losses) = ? AND wins > ?)
         OR ((wins - losses) = ? AND wins = ? AND created_at < ?)
          )
"""


def _row_to_entry(row: dict, rank: int) -> dict:
    return {
        "rank": rank,
        "display_name": row["display_name"],
        "wins": row["wins"],
        "losses": row["losses"],
        "ties": row["ties"],
        "score": row["score"],
    }


def compute_leaderboard(request: Request) -> dict:
    """Shared by the JSON API route and the server-rendered page route."""
    rows = db.query_dicts(TOP_SQL)
    top = [_row_to_entry(row, i + 1) for i, row in enumerate(rows)]

    me = None
    token = request.cookies.get(auth.COOKIE_NAME)
    profile = auth.get_profile_for_token(token) if token else None
    if profile is not None:
        qualifies = (profile["wins"] + profile["losses"] + profile["ties"]) >= 5
        already_in_top = any(row["id"] == profile["id"] for row in rows[:10])
        if qualifies and not already_in_top:
            score = profile["wins"] - profile["losses"]
            rank_row = db.query_one_dict(
                MY_RANK_SQL,
                (score, score, profile["wins"], score, profile["wins"], profile["created_at"]),
            )
            me = {
                "rank": rank_row["my_rank"],
                "display_name": profile["display_name"],
                "wins": profile["wins"],
                "losses": profile["losses"],
                "ties": profile["ties"],
                "score": score,
            }

    return {"top": top, "me": me}


@router.get("/api/leaderboard")
async def get_leaderboard(request: Request):
    return JSONResponse(compute_leaderboard(request), status_code=200)
