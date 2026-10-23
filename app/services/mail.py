"""TLS-only transactional email. No console sender or plaintext code logging."""
import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import Annotated, Protocol

from fastapi import Depends, HTTPException
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class Mailer(Protocol):
    def send_code(self, email: str, code: str, purpose: str) -> None: ...
    def send_password_changed(self, email: str) -> None: ...


class SMTPMailer:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _send(self, recipient: str, subject: str, body: str):
        settings = self.settings
        message = EmailMessage()
        message['From'] = str(settings.smtp_from)
        message['To'] = recipient
        message['Subject'] = subject
        message.set_content(body)
        context = ssl.create_default_context()
        if settings.smtp_security == 'tls':
            connection = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port,
                                          timeout=settings.smtp_timeout_seconds, context=context)
        else:
            connection = smtplib.SMTP(settings.smtp_host, settings.smtp_port,
                                       timeout=settings.smtp_timeout_seconds)
        with connection:
            if settings.smtp_security == 'starttls':
                connection.ehlo()
                connection.starttls(context=context)
                connection.ehlo()
            if settings.smtp_username:
                connection.login(settings.smtp_username, settings.smtp_password.get_secret_value())
            connection.send_message(message)

    def send_code(self, email: str, code: str, purpose: str):
        action = 'verify your email' if purpose == 'registration' else 'reset your password'
        self._send(email, f'PathBridge AI — {action}',
                   f'Your PathBridge AI code to {action} is:\n\n{code}\n\n'
                   'This code expires in 10 minutes and can be used once.\n'
                   'Enter it only in the PathBridge page where you started this request.\n'
                   'Never share this code. If you did not request it, ignore this email.\n')

    def send_password_changed(self, email: str):
        self._send(email, 'PathBridge AI — your password was changed',
                   'Your PathBridge AI password was changed. All previous sessions were signed out.\n'
                   'If you did not make this change, contact your school support team immediately.\n')


def get_mailer(settings: Annotated[Settings, Depends(get_settings)]) -> Mailer:
    if not settings.smtp_host or not settings.smtp_from or len(settings.auth_code_secret.get_secret_value()) < 32:
        raise HTTPException(503, 'Email delivery is not configured. Please contact your school support team.')
    return SMTPMailer(settings)


def deliver_code(mailer: Mailer, email: str, code: str, purpose: str):
    try:
        mailer.send_code(email, code, purpose)
    except (OSError, smtplib.SMTPException):
        # SMTP exception strings may include recipient addresses. Never log them.
        logger.error('Transactional code email could not be delivered; check the mail service.')


def deliver_password_changed(mailer: Mailer, email: str):
    try:
        mailer.send_password_changed(email)
    except (OSError, smtplib.SMTPException):
        logger.error('Password-change notification could not be delivered; check the mail service.')
