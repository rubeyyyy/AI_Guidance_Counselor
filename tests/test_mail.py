import smtplib
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services.mail import SMTPMailer, deliver_code


def settings(**overrides):
    values = dict(_env_file=None, smtp_host='smtp.example.org', smtp_from='pathbridge@example.org',
                  smtp_username='service-user', smtp_password='test-only-smtp-secret',
                  auth_code_secret='test-only-code-secret-of-at-least-32-characters')
    values.update(overrides)
    return Settings(**values)


def test_smtp_requires_tls_before_authentication(monkeypatch):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    factory = MagicMock(return_value=connection)
    monkeypatch.setattr(smtplib, 'SMTP', factory)
    mailer = SMTPMailer(settings())
    mailer.send_code('synthetic@example.org', '12345678', 'registration')
    factory.assert_called_once_with('smtp.example.org', 587, timeout=10)
    methods = [call[0] for call in connection.method_calls]
    assert methods.index('starttls') < methods.index('login') < methods.index('send_message')
    message = connection.send_message.call_args.args[0]
    assert message['To'] == 'synthetic@example.org'
    assert '12345678' in message.get_content()
    assert '10 minutes' in message.get_content()
    assert 'assessment' not in message.get_content()


def test_smtp_implicit_tls_and_notification(monkeypatch):
    connection = MagicMock()
    factory = MagicMock(return_value=connection)
    monkeypatch.setattr(smtplib, 'SMTP_SSL', factory)
    SMTPMailer(settings(smtp_security='tls', smtp_port=465)).send_password_changed('synthetic@example.org')
    assert factory.call_args.args == ('smtp.example.org', 465)
    connection.starttls.assert_not_called()
    assert 'password was changed' in connection.send_message.call_args.args[0].get_content()


def test_mail_errors_do_not_log_recipient_code_or_credentials(caplog):
    mailer = MagicMock()
    mailer.send_code.side_effect = smtplib.SMTPException('private@example.org 12345678 smtp-password')
    deliver_code(mailer, 'private@example.org', '12345678', 'password_reset')
    assert 'could not be delivered' in caplog.text
    assert all(value not in caplog.text for value in ['private@example.org', '12345678', 'smtp-password'])


def test_email_settings_fail_closed():
    for overrides in [dict(auth_code_secret='short'), dict(smtp_from=None),
                      dict(smtp_password=''), dict(smtp_security='plain')]:
        with pytest.raises(ValidationError):
            settings(**overrides)


def test_blank_optional_sender_in_env_example_is_valid():
    settings = Settings(_env_file=None, smtp_from='', smtp_host='')
    assert settings.smtp_from is None


def test_invalid_configuration_does_not_echo_secrets():
    with pytest.raises(ValidationError) as error:
        settings(auth_code_secret='private-invalid-code-key', smtp_password='private-smtp-password')
    assert 'private-invalid-code-key' not in str(error.value)
    assert 'private-smtp-password' not in str(error.value)
