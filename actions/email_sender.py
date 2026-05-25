# email_sender.py
"""Send an email via Gmail SMTP.

Requires two values in config/api_keys.json:
  "email_address"      — your Gmail address
  "email_app_password" — a Gmail App Password (NOT your normal password;
                         create one at https://myaccount.google.com/apppasswords)

Recipients can be given as a literal address, or as a contact name stored in
config under an "email_contacts" map, e.g.
  "email_contacts": {"gaurav": "gaurav@example.com"}
"""
import json
import re
import smtplib
import sys
from email.mime.text import MIMEText
from pathlib import Path

_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 587
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _config() -> dict:
    try:
        return json.loads(
            (_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8")
        )
    except Exception:
        return {}


def _resolve_recipient(to: str, cfg: dict) -> str | None:
    to = to.strip()
    if _EMAIL_RE.match(to):
        return to
    contacts = {k.lower(): v for k, v in cfg.get("email_contacts", {}).items()}
    return contacts.get(to.lower())


def send_email(parameters: dict, response=None, player=None,
               session_memory=None) -> str:
    cfg = _config()
    sender = str(cfg.get("email_address", "")).strip()
    password = str(cfg.get("email_app_password", "")).strip()

    if not sender or not password or password.startswith("PASTE_"):
        return ("Email is not configured. Add 'email_address' and a Gmail "
                "'email_app_password' to config/api_keys.json.")

    params = parameters or {}
    to_raw = str(params.get("to", "")).strip()
    subject = str(params.get("subject", "(no subject)")).strip()
    body = str(params.get("body", "")).strip()

    if not to_raw:
        return "Please specify a recipient email address or contact name."
    if not body:
        return "Please specify the email body."

    recipient = _resolve_recipient(to_raw, cfg)
    if not recipient:
        return (f"'{to_raw}' is not a valid email and isn't in your "
                f"email_contacts. Please provide an email address.")

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    print(f"[Email] ✉️  → {recipient}: {subject}")
    try:
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, recipient, msg.as_string())
    except smtplib.SMTPAuthenticationError:
        return ("Gmail rejected the login. Make sure you're using a Gmail "
                "App Password, not your account password.")
    except Exception as e:
        return f"Could not send email: {e}"

    result = f"Email sent to {recipient}."
    if player:
        player.write_log(f"[email] → {recipient}")
    return result
