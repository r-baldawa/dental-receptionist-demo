"""
Gmail SMTP integration — OAuth2 (refresh-token flow).

PHIPA hard requirement: one individually addressed email per patient.
`to` is intentionally a single str, never a list — enforced at the call site.
"""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

load_dotenv()


def _get_access_token() -> tuple[str, str]:
    """Return (sender_address, fresh_access_token) using the stored refresh token."""
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
    )
    creds.refresh(Request())
    return os.environ["GMAIL_SENDER_ADDRESS"], creds.token


def send_email(
    to: str,
    subject: str,
    body: str,
    bcc: str | None = None,
) -> bool:
    """Send one email to one recipient. Returns True on success.

    `to` is intentionally a single str, not a list — enforces the one-email-per-patient
    requirement at the call site. See plan.md Phase 4 and CLAUDE.md non-negotiables.
    """
    sender, token = _get_access_token()

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    if bcc:
        msg["Bcc"] = bcc
    msg.attach(MIMEText(body, "plain", "utf-8"))

    to_addrs = [addr.strip() for addr in to.split(",") if addr.strip()]
    recipients = to_addrs + ([bcc] if bcc else [])

    # smtp.auth() base64-encodes the return value internally, so pass the raw payload.
    raw_auth = f"user={sender}\x01auth=Bearer {token}\x01\x01"

    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.auth("XOAUTH2", lambda _=None: raw_auth)
        smtp.sendmail(sender, recipients, msg.as_string())

    print(f"[gmail_smtp] sent → {to!r}  subject={subject!r}")
    return True


def send_emergency_alert(captured_info: dict) -> bool:
    """Send emergency alert to the clinic's emergency-intake address.

    Fires with whatever has been captured so far — completeness is not the priority.
    See dental_agent_unified_system_design_v3.md §2 Emergency handling.
    """
    alert_email = os.environ.get("CLINIC_EMERGENCY_ALERT_EMAIL", "")
    if not alert_email:
        print("[gmail_smtp] WARNING: CLINIC_EMERGENCY_ALERT_EMAIL not set — alert not sent")
        return False

    body_lines = ["DENTAL EMERGENCY ALERT", "-" * 40]
    for k, v in captured_info.items():
        body_lines.append(f"{k}: {v}")

    return send_email(
        to=alert_email,
        subject="URGENT: Dental Emergency Alert",
        body="\n".join(body_lines),
    )
