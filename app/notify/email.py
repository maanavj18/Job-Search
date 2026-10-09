from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


def send_digest(drafts: list[dict]) -> bool:
    host = os.environ.get("SMTP_HOST", "").strip()
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "").strip()
    recipient = os.environ.get("NOTIFY_TO", "").strip()
    if not drafts or not (host and user and password and recipient):
        return False
    port = int(os.environ.get("SMTP_PORT", "587"))
    lines = [f"{len(drafts)} new internship draft(s) are ready to review.", ""]
    for draft in drafts[:30]:
        lines.append(f"- {draft['company']}: {draft['title']} ({draft['location']})")
        lines.append(f"  {draft['url']}")
    lines.append("")
    lines.append("Open the review page with: python -m app.cli serve")
    lines.append("http://127.0.0.1:8000")
    message = EmailMessage()
    message["Subject"] = f"{len(drafts)} internship draft(s) ready"
    message["From"] = user
    message["To"] = recipient
    message.set_content("\n".join(lines))
    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(message)
    return True
