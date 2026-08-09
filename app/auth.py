"""
Session cookie issuing/reading, sign-in/create-profile logic, PIN hashing.
(DESIGN.md Section 4.1, Section 7. PRD FR-15, FR-18-24, Q4.)
"""

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from app import db

COOKIE_NAME = "session_token"
COOKIE_MAX_AGE = 31536000  # 1 year, seconds

NAME_RE = re.compile(r"^[A-Za-z0-9_-]{3,20}$")
PIN_RE = re.compile(r"^\d{4}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# PIN recovery tuning (DESIGN_V2.md Section 1.3).
PIN_RESET_TOKEN_TTL_SECONDS = 30 * 60  # 30 minutes
PIN_RESET_COOLDOWN_SECONDS = 60


class ValidationError(Exception):
    """Raised for malformed name/PIN input (FR-21) -> maps to 422."""


class NameTakenError(Exception):
    """Raised by create_profile_explicit() when the display name already
    exists (FR-18) -> maps to 409. Nothing is created or modified."""


class SignInFailedError(Exception):
    """Raised by sign_in() when the name doesn't exist OR exists with the
    wrong PIN (FR-19) -> maps to 401. Deliberately a single error type for
    both cases so the response can't be used to probe which names exist."""


class InvalidResetTokenError(Exception):
    """Raised by reset_pin_with_token() when the token is missing,
    unrecognized, expired, or already used (DESIGN_V2.md Section 1.4)."""


def _iso_now() -> str:
    """Same ISO-8601-with-milliseconds format as SQLite's own
    strftime('%Y-%m-%dT%H:%M:%fZ','now') default, so Python-computed and
    DB-computed timestamps compare correctly as plain strings."""
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _iso_plus_seconds(seconds: int) -> str:
    dt = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def validate_display_name(name) -> str:
    if name is None:
        raise ValidationError("display_name is required")
    if not isinstance(name, str):
        raise ValidationError("display_name must be a string")
    name = name.strip()
    if not name:
        raise ValidationError("display_name cannot be empty")
    if not NAME_RE.match(name):
        raise ValidationError(
            "display_name must be 3-20 characters: letters, numbers, underscore, or hyphen only"
        )
    return name


def validate_pin(pin) -> str:
    if pin is None:
        raise ValidationError("pin is required")
    if not isinstance(pin, str):
        raise ValidationError("pin must be a string")
    pin = pin.strip()
    if not PIN_RE.match(pin):
        raise ValidationError("pin must be exactly 4 digits")
    return pin


def validate_recovery_email(email) -> Optional[str]:
    """
    Recovery email is optional at profile creation (PRD_V2 Q1/FR-38) --
    None/empty is fine and means "no recovery configured" (NULL in the
    DB). If something IS provided, it must look like an email address.
    """
    if email is None:
        return None
    if not isinstance(email, str):
        raise ValidationError("recovery_email must be a string")
    email = email.strip()
    if not email:
        return None
    if not EMAIL_RE.match(email):
        raise ValidationError("recovery_email must be a valid email address")
    return email


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


def create_profile(display_name: str, pin: str, recovery_email: Optional[str] = None) -> dict:
    salt = secrets.token_hex(8)
    pin_hash = hash_pin(pin, salt)
    cur = db.execute(
        "INSERT INTO profiles (display_name, pin_hash, pin_salt, recovery_email) VALUES (?, ?, ?, ?)",
        (display_name, pin_hash, salt, recovery_email),
    )
    return get_profile_by_id(cur.lastrowid)


def create_profile_explicit(display_name: str, pin: str, recovery_email: Optional[str] = None) -> dict:
    """
    "Create Account" (FR-18), a genuinely separate action from signing in
    (2026-08-06 revision -- see PRD FR-18). Succeeds only if the name
    doesn't already exist; otherwise raises NameTakenError and creates
    nothing. recovery_email is optional (v2, FR-38/Q1) -- None means "no
    recovery configured."
    """
    existing = get_profile_by_name(display_name)
    if existing is not None:
        raise NameTakenError()
    return create_profile(display_name, pin, recovery_email)


def sign_in(display_name: str, pin: str) -> dict:
    """
    "Sign In" (FR-19, 2026-08-06 revision). Succeeds only if the name
    exists AND the PIN matches. If the name doesn't exist, or exists with
    the wrong PIN, raises the same SignInFailedError either way -- no
    account is ever created here, and the failure never reveals which
    case it was.
    """
    existing = get_profile_by_name(display_name)
    if existing is None:
        raise SignInFailedError()

    expected = hash_pin(pin, existing["pin_salt"])
    if not secrets.compare_digest(expected, existing["pin_hash"]):
        raise SignInFailedError()
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


# --- PIN recovery (v2, DESIGN_V2.md Section 1) ---------------------------


def recovery_email_matches(profile: dict, submitted_email: str) -> bool:
    """Case-insensitive comparison against the profile's on-file
    recovery_email. False if the profile has none configured."""
    on_file = profile.get("recovery_email")
    if not on_file or not isinstance(submitted_email, str):
        return False
    return on_file.strip().lower() == submitted_email.strip().lower()


def is_recovery_cooldown_active(profile_id: int) -> bool:
    """60s per-profile cooldown between successful sends (Section 1.3),
    checked against the most recent pin_resets.created_at for this
    profile regardless of used_at."""
    row = db.query_one_dict(
        "SELECT created_at FROM pin_resets WHERE profile_id = ? ORDER BY created_at DESC LIMIT 1",
        (profile_id,),
    )
    if row is None:
        return False
    cutoff = _iso_plus_seconds(-PIN_RESET_COOLDOWN_SECONDS)
    return row["created_at"] > cutoff


def create_pin_reset_token(profile_id: int) -> str:
    """
    Generates a new one-time reset token for this profile. Any previously
    issued, not-yet-used token for this profile is deleted first, so only
    the most recently emailed link ever works (Section 1.3) -- used/
    expired history is left alone (kept as an audit trail, same reasoning
    v1 applied to game_results).
    """
    db.execute(
        "DELETE FROM pin_resets WHERE profile_id = ? AND used_at IS NULL",
        (profile_id,),
    )
    token = secrets.token_urlsafe(32)
    expires_at = _iso_plus_seconds(PIN_RESET_TOKEN_TTL_SECONDS)
    db.execute(
        "INSERT INTO pin_resets (token, profile_id, expires_at) VALUES (?, ?, ?)",
        (token, profile_id, expires_at),
    )
    return token


def get_valid_pin_reset(token) -> Optional[dict]:
    """Returns the pin_resets row if the token is recognized, unused, and
    unexpired -- else None. Used both by the GET /reset-pin page (to
    decide whether to show the form) and by reset_pin_with_token()."""
    if not isinstance(token, str) or not token:
        return None
    row = db.query_one_dict("SELECT * FROM pin_resets WHERE token = ?", (token,))
    if row is None:
        return None
    if row["used_at"] is not None:
        return None
    if row["expires_at"] < _iso_now():
        return None
    return row


def reset_pin_with_token(token, new_pin: str) -> dict:
    """
    Validates the token, then updates the PIN, marks the token used, and
    deletes all sessions for that profile -- kept as one function so
    those three steps always happen together (DESIGN_V2.md Section 1.4;
    note: v1's existing multi-step DB writes, e.g. game finalize, are
    likewise sequential `db.execute()` calls rather than a real DB
    transaction -- this follows the same established pattern, not a new
    gap introduced here).
    """
    reset_row = get_valid_pin_reset(token)
    if reset_row is None:
        raise InvalidResetTokenError()

    profile_id = reset_row["profile_id"]
    salt = secrets.token_hex(8)
    pin_hash = hash_pin(new_pin, salt)
    db.execute(
        "UPDATE profiles SET pin_hash = ?, pin_salt = ? WHERE id = ?",
        (pin_hash, salt, profile_id),
    )
    db.execute(
        "UPDATE pin_resets SET used_at = ? WHERE token = ?",
        (_iso_now(), reset_row["token"]),
    )
    db.execute("DELETE FROM sessions WHERE profile_id = ?", (profile_id,))
    return get_profile_by_id(profile_id)
