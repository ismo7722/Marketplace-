"""Email reminder when Facebook manual login is still pending."""
from __future__ import annotations

import logging

from app.config import get_settings
from app.database import SessionLocal
from app.models import LogCategory, LogLevel, NotificationRecipient
from app.services.email_service import email_service
from app.services.log_service import log_activity_isolated

logger = logging.getLogger(__name__)

LOGIN_REMINDER_AFTER_SECONDS = 300  # 5 minutes after browser opens

LOGIN_REMINDER_HTML = """
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; padding: 32px; background: #f4f6f9;">
  <div style="max-width: 520px; margin: 0 auto; background: white; padding: 28px; border-radius: 12px;">
    <h2 style="color: #1877f2; margin-top: 0;">Facebook login required</h2>
    <p>The monitoring bot opened the browser but Facebook is not logged in yet.</p>
    <p><strong>Please open the Chromium window and log in to Facebook manually</strong> (including any 2FA).</p>
    <p style="color: #65676b; font-size: 14px;">Monitoring will continue automatically once login is complete.</p>
    <p style="color: #65676b; font-size: 12px; margin-top: 24px;">Facebook Marketplace Monitor</p>
  </div>
</body>
</html>
"""


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


async def send_facebook_login_reminder() -> bool:
    """Send one login reminder to admin + alert recipients. Returns True if any email sent."""
    recipients = _reminder_recipients()
    if not recipients:
        log_activity_isolated(
            LogCategory.NOTIFICATION,
            "Login reminder skipped — no admin or alert email configured",
            level=LogLevel.WARNING,
            source="facebook",
        )
        return False

    settings = get_settings()
    smtp = settings.smtp_config_dict()
    subject = "Action required — log in to Facebook for Marketplace monitoring"
    sent_any = False
    errors: list[str] = []

    for to_email in recipients:
        ok, msg = await email_service.send_email(to_email, subject, LOGIN_REMINDER_HTML, smtp)
        if ok:
            sent_any = True
            logger.info("Facebook login reminder sent to %s", to_email)
        else:
            errors.append(f"{to_email}: {msg}")

    if sent_any:
        log_activity_isolated(
            LogCategory.NOTIFICATION,
            "Facebook login reminder email sent — please log in manually in the browser",
            details={"recipients": recipients},
            source="facebook",
        )
    elif errors:
        log_activity_isolated(
            LogCategory.ERROR,
            "Could not send Facebook login reminder email",
            level=LogLevel.ERROR,
            details={"errors": errors},
            source="facebook",
        )
    return sent_any
