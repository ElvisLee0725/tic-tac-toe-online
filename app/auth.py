"""
Session cookie issuing/reading, sign-in/create-profile logic, PIN hashing.
(DESIGN.md Section 4.1, Section 7. PRD FR-15, FR-18-24, Q4.)
"""

import hashlib
import re
import secrets
from typing import Optional, Tuple

from app import db

COOKIE_NAME = "session_token"
COOKIE_MAX_AGE = 31536000  # 1 year, seconds

NAME_RE = re.compile(r"^[A-Za-z0-9_-]{3,20}$")
PIN_RE = re.compile(r"^\d{4}$")


class ValidationError(Exception):
    """Raised for malformed name/PIN input (FR-21) -> maps to 422."""


class WrongPinError(Exception):
    """Raised when an existing name is used with an incorrect PIN (FR-20) -> maps to 401."""


def validate_display_name(name: str) -> str:
    if name is None:
        raise ValidationError("display_name is required")
    name = name.strip()
    if not name:
        raise ValidationError("display_name cannot be empty")
    if not NAME_RE.match(name):
        raise ValidationError(
            "display_name must be 3-20 characters: letters, numbers, underscore, or hyphen only"
        )
    return name


def validate_pin(pin: str) -> str:
    if pin is None:
        raise ValidationError("pin is required")
    pin = pin.strip()
    if not PIN_RE.match(pin):
        raise ValidationError("pin must be exactly 4 digits")
    return pin


def hash_pin(pin: str, salt: str) -> str:
    return hashlib.sha256((salt + pin).encode("utf-8")).hexdigest()


def profile_to_dict(row: dict) -> dict:
    return {
        "id": row["id"],
        "display_name": row["display_name"],
        "wins": row["wins"],
        "losses": row["losses"],
        "ties": row["ties"],
        "created_at": row["created_at"],
    }


def get_profile_by_name(display_name: str) -> Optional[dict]:
    return db.query_one_dict(
        "SELECT * FROM profiles WHERE display_name = ? COLLATE NOCASE",
        (display_name,),
    )


def get_profile_by_id(profile_id: int) -> Optional[dict]:
    return db.query_one_dict("SELECT * FROM profiles WHERE id = ?", (profile_id,))


def create_profile(display_name: str, pin: str) -> dict:
    salt = secrets.token_hex(8)
    pin_hash = hash_pin(pin, salt)
    cur = db.execute(
        "INSERT INTO profiles (display_name, pin_hash, pin_salt) VALUES (?, ?, ?)",
        (display_name, pin_hash, salt),
    )
    return get_profile_by_id(cur.lastrowid)


def create_or_signin(display_name: str, pin: str) -> dict:
    """
    Combined create-or-signin logic (FR-18/19/20), shared by POST /api/session
    and (later) the vs-Human opponent sign-in flow.

    - Name doesn't exist -> create a new profile.
    - Name exists, PIN matches -> return that profile.
    - Name exists, PIN doesn't match -> raise WrongPinError.
    """
    existing = get_profile_by_name(display_name)
    if existing is None:
        return create_profile(display_name, pin)

    expected = hash_pin(pin, existing["pin_salt"])
    if not secrets.compare_digest(expected, existing["pin_hash"]):
        raise WrongPinError()
    return existing


def create_session(profile_id: int) -> str:
    token = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO sessions (token, profile_id) VALUES (?, ?)",
        (token, profile_id),
    )
    return token


def delete_session(token: str) -> None:
    db.execute("DELETE FROM sessions WHERE token = ?", (token,))


def get_profile_for_token(token: str) -> Optional[dict]:
    if not token:
        return None
    row = db.query_one_dict("SELECT profile_id FROM sessions WHERE token = ?", (token,))
    if row is None:
        return None
    return get_profile_by_id(row["profile_id"])
