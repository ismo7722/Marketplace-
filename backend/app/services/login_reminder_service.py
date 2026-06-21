"""Email when Facebook session is missing or expired on the server."""
from __future__ import annotations

import logging
import time

from app.config import get_settings
from app.database import SessionLocal
from app.models import LogCategory, LogLevel, NotificationRecipient
from app.services.email_service import email_service
from app.services.log_service import log_activity_isolated

logger = logging.getLogger(__name__)

LOGIN_REMINDER_AFTER_SECONDS = 300
LOGOUT_EMAIL_COOLDOWN_SECONDS = 3600
_last_logout_email_at: float = 0.0

LOGOUT_ALERT_HTML = """
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; padding: 32px; background: #f4f6f9;">
  <div style="max-width: 520px; margin: 0 auto; background: white; padding: 28px; border-radius: 12px;">
    <h2 style="color: #1877f2; margin-top: 0;">Facebook login required</h2>
    <p>Marketplace monitoring is ON but Facebook is logged out.</p>
    <p><strong>On your PC, run:</strong></p>
    <p style="background:#f0f2f5;padding:12px;border-radius:8px;font-family:monospace;">login-facebook.bat</p>
    <ol style="color:#333;line-height:1.6;">
      <li>Chromium opens — log in to Facebook (2FA ok)</li>
      <li>Session saves automatically</li>
      <li>Dashboard → Stop → Start — 5-step monitoring runs headless on the server</li>
    </ol>
    <p style="color: #65676b; font-size: 12px; margin-top: 24px;">Facebook Marketplace Monitor</p>
  </div>
</body>
</html>
"""

LOGIN_REMINDER_HTML = LOGOUT_ALERT_HTML


def _reminder_recipients() -> list[str]:
    settings = get_settings()
    emails: list[str] = []
    admin = (settings.ADMIN_EMAIL or "").strip().lower()
    if admin and "@" in admin:
        emails.append(admin)

    db = SessionLocal()
    try:
        rows = db.query(NotificationRecipient).filter(NotificationRecipient.is_active == True).all()
        for row in rows:
            addr = (row.email or "").strip().lower()
            if addr and "@" in addr and addr not in emails:
                emails.append(addr)
    finally:
        db.close()
    return emails


async def send_facebook_logout_alert() -> bool:
    """One email per hour when bot detects Facebook logout on the server."""
    global _last_logout_email_at
    now = time.monotonic()
    if now - _last_logout_email_at < LOGOUT_EMAIL_COOLDOWN_SECONDS:
        return False

    recipients = _reminder_recipients()
    if not recipients:
        return False

    settings = get_settings()
    smtp = settings.smtp_config_dict()
    subject = "Action required — run login-facebook.bat to sign in to Facebook"
    sent_any = False

    for to_email in recipients:
        ok, _msg = await email_service.send_email(to_email, subject, LOGOUT_ALERT_HTML, smtp)
        if ok:
            sent_any = True
            logger.info("Facebook logout alert sent to %s", to_email)

    if sent_any:
        _last_logout_email_at = now
        log_activity_isolated(
            LogCategory.NOTIFICATION,
            "Email sent — run login-facebook.bat on your PC to sign in to Facebook",
            details={"recipients": recipients},
            source="facebook",
        )
    return sent_any


async def send_facebook_login_reminder() -> bool:
    """Visible-browser mode only — reminder after 5 minutes waiting for login."""
    return await send_facebook_logout_alert()
