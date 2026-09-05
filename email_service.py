"""
Sends the weekly digest email via plain SMTP (works with a Gmail "App
Password" out of the box: https://myaccount.google.com/apppasswords).
Swap send_email()'s internals for SendGrid/Resend/etc. if you'd rather use
an API-based provider — nothing else in the app needs to change.
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.config import settings


def send_email(subject: str, body_text: str, to_email: str | None = None) -> None:
    if not settings.smtp_user or not settings.smtp_password:
        raise RuntimeError("SMTP_USER / SMTP_PASSWORD not set in .env")

    to_email = to_email or settings.digest_to_email
    msg = MIMEMultipart()
    msg["From"] = settings.digest_from_email or settings.smtp_user
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body_text, "plain"))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)


def build_digest_text(tracker_entries: list[dict]) -> str:
    if not tracker_entries:
        return "No applications tracked yet this week. Time to browse some jobs!"

    lines = [f"Weekly Apply Assist digest — {len(tracker_entries)} application(s) tracked\n"]
    by_status: dict[str, list[dict]] = {}
    for e in tracker_entries:
        by_status.setdefault(e["status"], []).append(e)

    for status, entries in by_status.items():
        lines.append(f"\n{status} ({len(entries)})")
        for e in entries:
            lines.append(f"  - {e['job']['role']} at {e['job']['company']} ({e['job']['location']})")

    return "\n".join(lines)
