from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import main
from app.api.auth import digest, hasher
from app.models import Student
from app.models.auth import AuthSession, EmailChallenge, User
from app.models.conversation import utc_now
from app.services.mail import get_mailer
from tests.test_auth import PASSWORD, headers, register, secure_client  # noqa: F401

NEW_PASSWORD = 'A different synthetic passphrase 57!'


def start(client, email='synthetic@example.org'):
    response = client.post('/auth/register', json={'email': email, 'password': PASSWORD, 'display_name': 'Synthetic'}, headers=headers(client))
    assert response.status_code == 202
    return response.json()['challenge_id'], client.mailer.codes[-1][1]


def verify(client, challenge, code):
    return client.post('/auth/verify-email', json={'challenge_id': challenge, 'code': code}, headers=headers(client))


def request_reset(client, email='synthetic@example.org'):
    return client.post('/auth/forgot-password', json={'email': email}, headers=headers(client))


def reset(client, challenge, code, password=NEW_PASSWORD):
    return client.post('/auth/reset-password', json={'challenge_id': challenge, 'code': code, 'new_password': password}, headers=headers(client))


def test_no_student_or_session_until_email_verified(secure_client):
    client, engine = secure_client
    challenge, code = start(client)
    assert client.get('/auth/me').status_code == 401
    assert client.post('/auth/login', json={'email': 'synthetic@example.org', 'password': PASSWORD}, headers=headers(client)).status_code == 401
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Student)) == 0
        assert db.scalar(select(func.count()).select_from(User)) == 0
        row = db.get(EmailChallenge, challenge)
        assert row.code_hash != code and len(row.code_hash) == 64
        assert hasher.verify(row.password_hash, PASSWORD)
    response = verify(client, challenge, code)
    assert response.status_code == 201 and response.json()['user']['email_verified'] is True
    assert code not in response.text and PASSWORD not in response.text
    assert client.get('/auth/me').status_code == 200
    assert verify(client, challenge, code).status_code == 400
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Student)) == 1
        assert db.get(EmailChallenge, challenge).password_hash is None


def test_expired_and_exhausted_codes_cannot_be_used(secure_client):
    client, engine = secure_client
    challenge, code = start(client)
    with Session(engine) as db:
        db.get(EmailChallenge, challenge).expires_at = utc_now() - timedelta(seconds=1)
        db.commit()
    assert verify(client, challenge, code).status_code == 400
    challenge, code = start(client, 'another@example.org')
    wrong = '00000000' if code != '00000000' else '11111111'
    for _ in range(5):
        assert verify(client, challenge, wrong).status_code == 400
    assert verify(client, challenge, code).status_code == 400
    with Session(engine) as db:
        assert db.get(EmailChallenge, challenge).attempts == 5
        assert db.scalar(select(func.count()).select_from(User)) == 0


def test_resend_rotates_code_and_enforces_cooldown(secure_client):
    client, engine = secure_client
    challenge, code = start(client)
    payload = {'email': 'synthetic@example.org', 'challenge_id': challenge}
    count = len(client.mailer.codes)
    assert client.post('/auth/resend-verification', json=payload, headers=headers(client)).status_code == 202
    assert len(client.mailer.codes) == count
    with Session(engine) as db:
        row = db.get(EmailChallenge, challenge)
        row.sent_at = utc_now() - timedelta(seconds=61)
        row.attempts = 1
        db.commit()
    assert client.post('/auth/resend-verification', json=payload, headers=headers(client)).status_code == 202
    new_code = client.mailer.codes[-1][1]
    assert len(client.mailer.codes) == count + 1
    with Session(engine) as db:
        assert db.get(EmailChallenge, challenge).attempts == 1
    if new_code != code:
        assert verify(client, challenge, code).status_code == 400
    assert verify(client, challenge, new_code).status_code == 201


def test_multiple_pending_signups_cannot_replace_verified_password(secure_client):
    client, engine = secure_client
    first, first_code = start(client)
    second, second_code = start(client)
    assert verify(client, second, second_code).status_code == 201
    assert verify(client, first, first_code).status_code == 400
    count = len(client.mailer.codes)
    duplicate = client.post('/auth/register', json={'email': 'synthetic@example.org', 'password': NEW_PASSWORD}, headers=headers(client))
    assert duplicate.status_code == 202 and len(client.mailer.codes) == count
    with Session(engine) as db:
        user = db.scalar(select(User))
        assert hasher.verify(user.password_hash, PASSWORD)
        assert db.scalar(select(func.count()).select_from(Student)) == 1


def test_password_reset_revokes_sessions_is_single_use_and_requires_login(secure_client):
    client, engine = secure_client
    user = register(client).json()['user']
    raw = client.cookies.get('pathbridge_session')
    pending = request_reset(client)
    code = client.mailer.codes[-1][1]
    # Requesting recovery must not invalidate the existing password or sessions.
    assert client.get('/auth/me').status_code == 200
    assert reset(client, pending.json()['challenge_id'], code).status_code == 200
    assert client.get('/auth/me').status_code == 401
    assert reset(client, pending.json()['challenge_id'], code).status_code == 400
    with Session(engine) as db:
        assert db.get(AuthSession, digest(raw)).revoked_at
        assert hasher.verify(db.get(User, user['id']).password_hash, NEW_PASSWORD)
    assert client.mailer.notifications == ['synthetic@example.org']
    for password, status in [(PASSWORD, 401), (NEW_PASSWORD, 200)]:
        assert client.post('/auth/login', json={'email': 'synthetic@example.org', 'password': password}, headers=headers(client)).status_code == status


def test_reset_request_hides_account_existence_and_codes(secure_client):
    client, engine = secure_client
    register(client)
    known = request_reset(client)
    count = len(client.mailer.codes)
    unknown = request_reset(client, 'unknown@example.org')
    assert known.status_code == unknown.status_code == 202
    assert known.json()['message'] == unknown.json()['message']
    assert len(known.json()['challenge_id']) == len(unknown.json()['challenge_id']) == 43
    assert len(client.mailer.codes) == count
    assert reset(client, unknown.json()['challenge_id'], '12345678').status_code == 400
    assert client.mailer.codes[-1][1] not in known.text


def test_reset_code_expiry_attempt_limits_and_purpose_binding(secure_client):
    client, engine = secure_client
    registration, registration_code = start(client)
    assert reset(client, registration, registration_code).status_code == 400
    assert verify(client, registration, registration_code).status_code == 201
    pending = request_reset(client).json()['challenge_id']
    code = client.mailer.codes[-1][1]
    assert verify(client, pending, code).status_code == 400
    with Session(engine) as db:
        db.get(EmailChallenge, pending).expires_at = utc_now() - timedelta(seconds=1)
        db.commit()
    assert reset(client, pending, code).status_code == 400
    pending = request_reset(client).json()['challenge_id']
    code = client.mailer.codes[-1][1]
    wrong = '00000000' if code != '00000000' else '11111111'
    for _ in range(5):
        assert reset(client, pending, wrong).status_code == 400
    assert reset(client, pending, code).status_code == 400


def test_existing_unverified_accounts_require_inbox_recovery(secure_client):
    client, engine = secure_client
    with Session(engine) as db:
        student = Student(display_name='Preserved synthetic student')
        db.add(student)
        db.flush()
        user = User(email='legacy@example.org', password_hash=hasher.hash(PASSWORD), role='student', student_id=student.id)
        db.add(user)
        db.commit()
        original_id = student.id
    assert client.post('/auth/login', json={'email': 'legacy@example.org', 'password': PASSWORD}, headers=headers(client)).status_code == 403
    pending = request_reset(client, 'legacy@example.org').json()['challenge_id']
    assert reset(client, pending, client.mailer.codes[-1][1]).status_code == 200
    login = client.post('/auth/login', json={'email': 'legacy@example.org', 'password': NEW_PASSWORD}, headers=headers(client))
    assert login.status_code == 200 and login.json()['user']['student_id'] == original_id


def test_new_endpoints_require_csrf_and_service_is_fail_closed(secure_client):
    client, engine = secure_client
    challenge, code = start(client)
    for path, payload in [('/verify-email', {'challenge_id': challenge, 'code': code}),
                           ('/forgot-password', {'email': 'synthetic@example.org'}),
                           ('/resend-verification', {'email': 'synthetic@example.org', 'challenge_id': challenge}),
                           ('/resend-reset', {'email': 'synthetic@example.org', 'challenge_id': challenge}),
                           ('/reset-password', {'challenge_id': challenge, 'code': code, 'new_password': NEW_PASSWORD})]:
        assert client.post('/auth' + path, json=payload).status_code == 403
    main.app.dependency_overrides.pop(get_mailer)
    assert client.post('/auth/register', json={'email': 'no-mail@example.org', 'password': PASSWORD}, headers=headers(client)).status_code == 503
    assert client.post('/auth/forgot-password', json={'email': 'unknown@example.org'}, headers=headers(client)).status_code == 503
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == 0


def test_weak_reset_password_does_not_consume_code(secure_client):
    client, engine = secure_client
    register(client)
    challenge = request_reset(client).json()['challenge_id']
    code = client.mailer.codes[-1][1]
    response = reset(client, challenge, code, 'short')
    assert response.status_code == 422 and all('input' not in error for error in response.json()['detail'])
    assert reset(client, challenge, code).status_code == 200


def test_password_reset_resend_replaces_old_code(secure_client):
    client, engine = secure_client
    register(client)
    challenge = request_reset(client).json()['challenge_id']
    old = client.mailer.codes[-1][1]
    with Session(engine) as db:
        db.get(EmailChallenge, challenge).sent_at = utc_now() - timedelta(seconds=61)
        db.commit()
    result = client.post('/auth/resend-reset', json={'email': 'synthetic@example.org', 'challenge_id': challenge}, headers=headers(client))
    assert result.status_code == 202
    fresh = client.mailer.codes[-1][1]
    if fresh != old:
        assert reset(client, challenge, old).status_code == 400
    assert reset(client, challenge, fresh).status_code == 200


def test_request_limits_apply_before_email_delivery(secure_client):
    from app.core.config import Settings, get_settings
    from tests.test_auth import CODE_SECRET
    client, _ = secure_client
    main.app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, auth_rate_limit=1, auth_code_secret=CODE_SECRET)
    assert request_reset(client, 'unknown@example.org').status_code == 202
    assert request_reset(client, 'unknown@example.org').status_code == 429
    assert not client.mailer.codes


def test_ip_limit_is_separate_from_the_email_limit(secure_client):
    from app.core.config import Settings, get_settings
    from tests.test_auth import CODE_SECRET
    client, _ = secure_client
    main.app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, auth_ip_rate_limit=2, auth_rate_limit=100, auth_code_secret=CODE_SECRET)
    assert request_reset(client, 'first@example.org').status_code == 202
    assert request_reset(client, 'second@example.org').status_code == 202
    assert request_reset(client, 'third@example.org').status_code == 429
