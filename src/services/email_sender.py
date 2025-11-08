import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict
from src.core.logger import log
from src.core.config import settings


class EmailSender:
    """Email delivery service with multiple provider support."""
    
    def __init__(self):
        self.dry_run = settings.dry_run_mode
        log.info(f"Email sender initialized (dry_run={self.dry_run})")
    
    def send_email(self, to_email: str, subject: str, body: str) -> bool:
        """Send email via configured provider."""

        if self.dry_run:
            log.info(f"[DRY RUN] Would send email to {to_email}")
            log.debug(f"Subject: {subject}")
            log.debug(f"Body: {body[:100]}...")
            return True
        
        try:
            return self._send_smtp(to_email, subject, body)
        except Exception as e:
            log.error(f"Failed to send email to {to_email}: {e}")
            return False
    
    def _send_smtp(self, to_email: str, subject: str, body: str) -> bool:
        """Send via SMTP."""
        
        msg = MIMEMultipart()
        msg['From'] = settings.from_email
        msg['To'] = to_email
        msg['Subject'] = subject
        
        msg.attach(MIMEText(body, 'plain'))
        
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        
        log.info(f"Email sent to {to_email}")
        return True