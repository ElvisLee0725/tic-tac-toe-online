"""
Thin Resend wrapper: send_pin_reset_email(profile, token).
(DESIGN_V2.md Section 1.5.)

Local-dev / no-Resend-account-yet fallback (not in DESIGN_V2.md, added
for this increment so PIN recovery is testable right now): nobody has
set up a Resend account/API key yet -- that's a real prerequisite (a
verified sending domain, Section 1.5/Section 5) that happens later,
out-of-band, with the stakeholder. So, same pattern as db.py's Turso
local-file fallback: if RESEND_API_KEY is not set in the environment,
send_pin_reset_email() logs the reset link to the server console/logs
instead of calling Resend. If RESEND_API_KEY IS set, it calls Resend for
real. See README.md for more detail.
"""

import logging
import os

logger = logging.getLogger("app.email")

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:8000")

RESET_EMAIL_SUBJECT = "Reset your Tic Tac Toe Online PIN"


def _build_reset_email_body(display_name: str, reset_link: str) -> str:
    return (
        f"Hi {display_name},\n\n"
        f"Someone (hopefully you) requested a PIN reset for your Tic Tac Toe Online profile.\n\n"
        f"Reset your PIN here: {reset_link}\n\n"
        "This link expires in 30 minutes and can only be used once.\n\n"
        "Note: this is a casual-game recovery method, not bank-grade security -- it's only "
        "as secure as access to this email inbox. If you didn't request this, you can safely "
        "ignore this email; your PIN won't change unless the link above is used.\n"
    )


def send_pin_reset_email(profile: dict, token: str) -> None:
    """
    profile: a profile dict (must include display_name and recovery_email).
    token: the raw pin_resets token (never logged/displayed anywhere else).
    """
    reset_link = f"{PUBLIC_BASE_URL}/reset-pin?token={token}"
    body = _build_reset_email_body(profile["display_name"], reset_link)
    recipient = profile.get("recovery_email")

    if not RESEND_API_KEY:
        # Local-dev fallback: log instead of sending. Deliberately visible
        # at INFO level via both the logger and a plain print(), since
        # uvicorn's default config doesn't always surface app-level log
        # records to the console the same way print() reliably does.
        message = (
            "[pin-recovery] RESEND_API_KEY not set -- logging instead of sending.\n"
            f"  To: {recipient}\n"
            f"  Subject: {RESET_EMAIL_SUBJECT}\n"
            f"  Reset link: {reset_link}"
        )
        logger.info(message)
        print(message)
        return

    import resend  # imported lazily so the package is only required when actually sending

    resend.api_key = RESEND_API_KEY
    resend.Emails.send(
        {
            # Placeholder sender address -- swap for a verified sending
            # domain once one exists (DESIGN_V2.md Section 1.5/Section 5,
            # V4). Not functional for arbitrary real recipients until then.
            "from": "Tic Tac Toe Online <onboarding@resend.dev>",
            "to": recipient,
            "subject": RESET_EMAIL_SUBJECT,
            "text": body,
        }
    )
