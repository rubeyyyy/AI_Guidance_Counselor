from datetime import timedelta
import json
from pathlib import Path

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import main
from app.api.auth import digest, hasher, require_counselor
from app.core.config import Settings, get_settings
from app.db.session import build_engine, get_db
from app.models import Student
from app.models.auth import AuthSession, User
from app.services.mail import get_mailer
from app.models.conversation import utc_now
from tests.migration_utils import migrate

ORIGIN = 'http://127.0.0.1:5173'
PASSWORD = 'Synthetic passphrase 42!'
CODE_SECRET = 'test-only-code-secret-with-more-than-32-characters'


class FakeMailer:
    def __init__(self):
        self.codes = []
        self.notifications = []

    def send_code(self, email, code, purpose):
        self.codes.append((email, code, purpose))

    def send_password_changed(self, email):
        self.notifications.append(email)


@pytest.fixture
def secure_client(tmp_path, monkeypatch):
    engine = build_engine(f"sqlite:///{tmp_path / 'auth.db'}")
    migrate(str(engine.url))
    monkeypatch.setattr(main, 'engine', engine)
    def database():
        with Session(engine) as db:
            yield db
    main.app.dependency_overrides[get_db] = database
    main.app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, auth_rate_limit=100, auth_code_secret=CODE_SECRET)
    mailer = FakeMailer()
    main.app.dependency_overrides[get_mailer] = lambda: mailer
    try:
        with TestClient(main.app) as client:
            client.mailer = mailer
            yield client, engine
    finally:
        main.app.dependency_overrides.clear()


def headers(client):
    return {'Origin': ORIGIN, 'X-CSRF-Token': client.get('/auth/csrf').json()['csrf_token']}


def register(client, email='synthetic@example.org'):
    count = len(client.mailer.codes)
    pending = client.post('/auth/register', json={'email': email, 'password': PASSWORD}, headers=headers(client))
    if pending.status_code != 202 or len(client.mailer.codes) == count:
        return pending
    code = client.mailer.codes[-1][1]
    return client.post('/auth/verify-email', json={'challenge_id': pending.json()['challenge_id'], 'code': code}, headers=headers(client))


def test_registration_ownership_and_password_hash(secure_client):
    client, engine = secure_client
    with Session(engine) as db:
        db.add(Student(display_name='Unclaimed synthetic legacy record'))
        db.commit()
    response = register(client)
    assert response.status_code == 201
    user = response.json()['user']
    assert user['role'] == 'student' and user['student_id'] != user['id']
    assert 'password' not in json.dumps(user)
    assert client.get('/auth/me').json() == user
    assert client.get(f"/students/{user['student_id']}").status_code == 200
    assert client.get('/students/1').status_code == 404
    assert client.post('/students', json={}, headers=headers(client)).status_code == 409
    with Session(engine) as db:
        stored = db.get(User, user['id'])
        assert hasher.verify(stored.password_hash, PASSWORD)
        raw = client.cookies.get('pathbridge_session')
        assert db.get(AuthSession, raw) is None
        assert db.get(AuthSession, digest(raw)).user_id == user['id']
        assert db.get(Student, 1).user is None
    assert 'HttpOnly' in response.headers['set-cookie']
    assert 'SameSite=lax' in response.headers['set-cookie']


def test_login_logout_revocation_and_generic_errors(secure_client):
    client, engine = secure_client
    register(client)
    raw = client.cookies.get('pathbridge_session')
    assert client.post('/auth/logout', headers=headers(client)).status_code == 200
    assert client.get('/auth/me').status_code == 401
    with Session(engine) as db:
        assert db.get(AuthSession, digest(raw)).revoked_at
    errors = []
    for email in ['synthetic@example.org', 'unknown@example.org']:
        result = client.post('/auth/login', json={'email': email, 'password': 'wrong'}, headers=headers(client))
        assert result.status_code == 401
        errors.append(result.json())
    assert errors[0] == errors[1]
    result = client.post('/auth/login', json={'email': 'SYNTHETIC@example.org', 'password': PASSWORD}, headers=headers(client))
    assert result.status_code == 200
    assert client.cookies.get('pathbridge_session') != raw
    assert client.get('/auth/me').status_code == 200
    client.cookies.clear()
    client.cookies.set('pathbridge_session', raw)
    assert client.get('/auth/me').status_code == 401


def test_csrf_required_for_registration_login_and_writes(secure_client):
    client, _ = secure_client
    payload = {'email': 'synthetic@example.org', 'password': PASSWORD}
    assert client.post('/auth/register', json=payload).status_code == 403
    good = headers(client)
    assert client.post('/auth/login', json=payload, headers={'Origin': ORIGIN}).status_code == 403
    assert client.post('/auth/register', json=payload, headers={**good, 'Origin': 'https://evil.example'}).status_code == 403
    assert client.post('/auth/register', json=payload, headers={**good, 'X-CSRF-Token': 'bad'}).status_code == 403
    assert register(client).status_code == 201
    assert client.post('/auth/logout', headers={'Origin': ORIGIN}).status_code == 403
    assert client.get('/auth/me').status_code == 200


def test_expiration_and_inactive_user(secure_client):
    client, engine = secure_client
    user = register(client).json()['user']
    with Session(engine) as db:
        db.get(User, user['id']).is_active = False
        db.commit()
    assert client.get('/auth/me').status_code == 401
    with Session(engine) as db:
        db.get(User, user['id']).is_active = True
        db.get(AuthSession, digest(client.cookies.get('pathbridge_session'))).expires_at = utc_now() - timedelta(seconds=1)
        db.commit()
    assert client.get('/auth/me').status_code == 401
    assert client.get(f"/students/{user['student_id']}").status_code == 401


def test_all_student_routes_enforce_ownership(secure_client):
    client, engine = secure_client
    first = register(client).json()['user']['student_id']
    second = register(client, 'other@example.org').json()['user']['student_id']
    assert first != second
    questions = client.get('/questionnaires/initial-v2/questions').json()
    qid = questions[0]['id']
    paths = ['', '/assessment', '/assessments/initial-v2/answers', '/assessments/initial-v2/progress',
             '/assessments/initial-v2/profile', '/conversations', '/conversations/1']
    for suffix in paths:
        assert client.get(f'/students/{first}{suffix}').status_code == 404
    for method, suffix, payload in [('put', '/assessment', {}),
        ('put', f'/assessments/initial-v2/answers/{qid}', {'value': 'synthetic'}),
        ('post', '/chat', {'message': 'synthetic'})]:
        assert getattr(client, method)(f'/students/{first}{suffix}', json=payload, headers=headers(client)).status_code == 404
    assert client.get(f'/students/{second}/assessments/initial-v2/progress').status_code == 200
    assert client.get(f'/students/{second}/conversations').json() == []
    assessment = json.loads(Path('examples/assessment.json').read_text())
    assert client.put(f'/students/{second}/assessment', json=assessment, headers=headers(client)).status_code == 200
    assert client.get(f'/students/{second}/assessment').json() == assessment
    client.cookies.clear()
    for suffix in paths:
        assert client.get(f'/students/{second}{suffix}').status_code == 401


def test_counselor_role_is_restricted(secure_client):
    client, engine = secure_client
    student_id = register(client).json()['user']['student_id']
    # A test-only app route exercises the reusable counselor dependency.
    from fastapi import FastAPI
    probe = FastAPI()
    @probe.get('/counselor', dependencies=[Depends(require_counselor)])
    def counselor():
        return {'ok': True}
    probe.dependency_overrides[get_db] = main.app.dependency_overrides[get_db]
    probe.dependency_overrides[get_settings] = main.app.dependency_overrides[get_settings]
    with TestClient(probe) as test:
        test.cookies.update(client.cookies)
        assert test.get('/counselor').status_code == 403
        with Session(engine) as db:
            db.add(User(email='counselor@example.org', password_hash=hasher.hash(PASSWORD), role='counselor', email_verified_at=utc_now()))
            db.commit()
        result = client.post('/auth/login', json={'email': 'counselor@example.org', 'password': PASSWORD}, headers=headers(client))
        assert result.status_code == 200
        test.cookies.update(client.cookies)
        assert test.get('/counselor').status_code == 200
        assert client.get(f'/students/{student_id}').status_code == 403
        assert client.post('/students', json={}, headers=headers(client)).status_code == 403
    assert client.post('/auth/register', json={'email': 'forbidden@example.org', 'password': PASSWORD, 'role': 'counselor'}, headers=headers(client)).status_code == 422


def test_validation_duplicate_and_rate_limit(secure_client):
    client, _ = secure_client
    for email, password in [('bad-email', PASSWORD), ('valid@example.org', 'short')]:
        response = client.post('/auth/register', json={'email': email, 'password': password}, headers=headers(client))
        assert response.status_code == 422
        assert all('input' not in error for error in response.json()['detail'])
    assert register(client).status_code == 201
    assert register(client).status_code == 202
    main.app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, auth_rate_limit=2)
    assert client.post('/auth/login', json={'email': 'synthetic@example.org', 'password': PASSWORD}, headers=headers(client)).status_code == 429


def test_production_cookie_configuration():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment='production')
    settings = Settings(_env_file=None, environment='production', cookie_secure=True, cors_origins=['https://pathbridge.example'])
    from app.api.auth import cookie_name
    assert cookie_name(settings).startswith('__Host-')
