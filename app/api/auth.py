"""Opaque sessions; tokens and credentials must never be logged."""
import hashlib
import hmac
import secrets
from datetime import timedelta
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import Student
from app.models.auth import AuthAttempt, AuthSession, EmailChallenge, User
from app.models.conversation import utc_now
from app.services.mail import Mailer, get_mailer, deliver_code, deliver_password_changed

DB = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
Mail = Annotated[Mailer, Depends(get_mailer)]
router = APIRouter(prefix='/auth', tags=['authentication'])
hasher = PasswordHasher()
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def cookie_name(settings):
    return '__Host-pathbridge_session' if settings.cookie_secure else 'pathbridge_session'


def session_for(request, db, settings):
    raw = request.cookies.get(cookie_name(settings), '')
    row = db.get(AuthSession, digest(raw)) if raw else None
    if row is None or row.revoked_at or row.expires_at <= utc_now():
        return None
    return row


def enforce_csrf(request: Request, db: DB, settings: Config):
    if request.method in {'GET', 'HEAD', 'OPTIONS'}:
        return
    origin = request.headers.get('origin')
    if origin not in settings.cors_origins:
        raise HTTPException(403, 'Request origin is not trusted')
    row = session_for(request, db, settings)
    token = request.headers.get('x-csrf-token', '')
    if not row or not secrets.compare_digest(row.csrf_hash, digest(token)):
        raise HTTPException(403, 'Security check failed. Refresh and try again.')


def get_current_user(request: Request, db: DB, settings: Config) -> User:
    row = session_for(request, db, settings)
    user = db.get(User, row.user_id) if row and row.user_id else None
    if user is None or not user.is_active or user.email_verified_at is None:
        raise HTTPException(401, 'Please sign in to continue')
    return user


def require_student(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != 'student':
        raise HTTPException(403, 'Student access required')
    return user


def require_counselor(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != 'counselor':
        raise HTTPException(403, 'Counselor access required')
    return user


def own_student(student_id: int, user: Annotated[User, Depends(require_student)]):
    if user.student_id != student_id:
        raise HTTPException(404, 'Student not found')


def issue_session(response, db, settings, user_id=None):
    raw = secrets.token_urlsafe(32)
    csrf = digest('csrf:' + raw)
    seconds = settings.session_hours * 3600 if user_id else 1800
    db.add(AuthSession(token_hash=digest(raw), csrf_hash=digest(csrf), user_id=user_id,
                       expires_at=utc_now() + timedelta(seconds=seconds)))
    response.set_cookie(cookie_name(settings), raw, max_age=seconds, httponly=True,
                        secure=settings.cookie_secure, samesite=settings.cookie_samesite, path='/')
    response.headers['Cache-Control'] = 'no-store'
    return csrf


def user_read(user):
    return {'id': user.id, 'email': user.email, 'role': user.role,
            'student_id': user.student_id, 'email_verified': user.email_verified_at is not None, 'created_at': user.created_at, 'is_active': user.is_active}


class Credentials(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value):
        return str(value).lower()


class Registration(Credentials):
    password: str = Field(min_length=12, max_length=128)
    display_name: str | None = Field(default=None, max_length=100)

    @field_validator('password')
    @classmethod
    def validate_password(cls, value):
        if not value.strip() or len(set(value)) < 4:
            raise ValueError('Choose a password with at least 12 characters and varied characters')
        return value


def throttle(request, db, settings, email):
    # DB-backed limits apply across workers. Do not trust forwarded IP headers.
    limits = [(digest('ip:' + (request.client.host if request.client else 'unknown')), settings.auth_ip_rate_limit),
              (digest('email:' + email), settings.auth_rate_limit)]
    cutoff = utc_now() - timedelta(minutes=15)
    for key, limit in limits:
        count = db.scalar(select(func.count()).select_from(AuthAttempt).where(
            AuthAttempt.key_hash == key, AuthAttempt.created_at > cutoff))
        if count >= limit:
            raise HTTPException(429, 'Too many attempts. Please try again later.', headers={'Retry-After': '900'})
    db.add_all([AuthAttempt(key_hash=key) for key, _ in limits])
    db.commit()


@router.get('/csrf')
def csrf(request: Request, response: Response, db: DB, settings: Config):
    response.headers['Cache-Control'] = 'no-store'
    row = session_for(request, db, settings)
    if row:
        token = digest('csrf:' + request.cookies[cookie_name(settings)])
    else:
        token = issue_session(response, db, settings)
        db.commit()
    return {'csrf_token': token}


CODE_MESSAGE = 'If this request can be completed, an email with a code will arrive shortly.'
CODE_FAILURE = 'The code is invalid or expired. Start a new request and try again.'
MAX_CODE_ATTEMPTS = 5


def code_digest(settings, challenge_id, purpose, code):
    secret = settings.auth_code_secret.get_secret_value()
    if len(secret) < 32:
        raise HTTPException(503, 'Email verification is not configured. Please contact your school support team.')
    return hmac.new(secret.encode(), f'{purpose}:{challenge_id}:{code}'.encode(), hashlib.sha256).hexdigest()


def new_challenge(db, settings, email, purpose, user_id=None, password_hash=None, display_name=None):
    identifier = secrets.token_urlsafe(32)
    code = f'{secrets.randbelow(100_000_000):08d}'
    row = EmailChallenge(id=identifier, email=email, purpose=purpose, user_id=user_id,
                         password_hash=password_hash, display_name=display_name,
                         code_hash=code_digest(settings, identifier, purpose, code),
                         expires_at=utc_now() + timedelta(minutes=10))
    db.add(row)
    return row, code


class EmailRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    email: EmailStr = Field(max_length=254)

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value):
        return str(value).lower()


class CodeRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    challenge_id: str = Field(min_length=43, max_length=43, pattern=r'^[A-Za-z0-9_-]+$')
    code: str = Field(min_length=8, max_length=8, pattern=r'^[0-9]{8}$')


class ResendRequest(EmailRequest):
    challenge_id: str = Field(min_length=43, max_length=43, pattern=r'^[A-Za-z0-9_-]+$')


class ResetRequest(CodeRequest):
    new_password: str = Field(min_length=12, max_length=128)

    @field_validator('new_password')
    @classmethod
    def validate_password(cls, value):
        return Registration.validate_password(value)


def consume_code(db, settings, payload, purpose):
    now = utc_now()
    row = db.get(EmailChallenge, payload.challenge_id)
    expected = code_digest(settings, payload.challenge_id, purpose, payload.code)
    valid = row and row.purpose == purpose and row.consumed_at is None and row.expires_at > now and row.attempts < MAX_CODE_ATTEMPTS
    if not valid or not secrets.compare_digest(row.code_hash, expected):
        # Count failed guesses atomically; resends never reset this budget.
        db.execute(update(EmailChallenge).where(
            EmailChallenge.id == payload.challenge_id,
            EmailChallenge.purpose == purpose,
            EmailChallenge.consumed_at.is_(None),
            EmailChallenge.expires_at > now,
            EmailChallenge.attempts < MAX_CODE_ATTEMPTS,
        ).values(attempts=EmailChallenge.attempts + 1))
        db.commit()
        raise HTTPException(400, CODE_FAILURE)
    consumed = db.execute(update(EmailChallenge).where(
        EmailChallenge.id == row.id, EmailChallenge.purpose == purpose,
        EmailChallenge.code_hash == expected, EmailChallenge.consumed_at.is_(None),
        EmailChallenge.expires_at > now, EmailChallenge.attempts < MAX_CODE_ATTEMPTS,
    ).values(consumed_at=now), execution_options={'synchronize_session': False})
    if consumed.rowcount != 1:
        db.rollback()
        raise HTTPException(400, CODE_FAILURE)
    return row


def invalidate_challenges(db, email):
    db.execute(update(EmailChallenge).where(EmailChallenge.email == email).values(
        consumed_at=utc_now(), password_hash=None), execution_options={'synchronize_session': False})


@router.post('/register', status_code=202)
def register(payload: Registration, request: Request, background: BackgroundTasks, db: DB, settings: Config, mailer: Mail):
    throttle(request, db, settings, payload.email)
    password_hash = hasher.hash(payload.password)
    identifier = secrets.token_urlsafe(32)
    if not db.scalar(select(User.id).where(User.email == payload.email)):
        row, code = new_challenge(db, settings, payload.email, 'registration',
                                  password_hash=password_hash, display_name=(payload.display_name or '').strip() or None)
        identifier = row.id
        db.commit()
        background.add_task(deliver_code, mailer, payload.email, code, 'registration')
    return {'message': CODE_MESSAGE, 'challenge_id': identifier}


@router.post('/verify-email', status_code=201)
def verify_email(payload: CodeRequest, request: Request, response: Response, db: DB, settings: Config):
    row = db.get(EmailChallenge, payload.challenge_id)
    throttle(request, db, settings, row.email if row else payload.challenge_id)
    row = consume_code(db, settings, payload, 'registration')
    if db.scalar(select(User.id).where(User.email == row.email)) or not row.password_hash:
        db.commit()
        raise HTTPException(400, CODE_FAILURE)
    student = Student(display_name=row.display_name)
    db.add(student)
    db.flush()
    user = User(email=row.email, password_hash=row.password_hash, role='student',
                student_id=student.id, email_verified_at=utc_now())
    db.add(user)
    try:
        db.flush()
        invalidate_challenges(db, row.email)
        previous = session_for(request, db, settings)
        if previous:
            previous.revoked_at = utc_now()
        token = issue_session(response, db, settings, user.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(400, CODE_FAILURE) from None
    return {'user': user_read(user), 'csrf_token': token}


def resend_code(payload, request, background, db, settings, mailer, purpose):
    throttle(request, db, settings, payload.email)
    now = utc_now()
    code = f'{secrets.randbelow(100_000_000):08d}'
    changed = db.execute(update(EmailChallenge).where(
        EmailChallenge.id == payload.challenge_id, EmailChallenge.email == payload.email,
        EmailChallenge.purpose == purpose, EmailChallenge.consumed_at.is_(None),
        EmailChallenge.attempts < MAX_CODE_ATTEMPTS,
        EmailChallenge.sent_at <= now - timedelta(seconds=60),
    ).values(code_hash=code_digest(settings, payload.challenge_id, purpose, code),
             sent_at=now, expires_at=now + timedelta(minutes=10)))
    db.commit()
    if changed.rowcount == 1:
        background.add_task(deliver_code, mailer, payload.email, code, purpose)
    return {'message': CODE_MESSAGE}


@router.post('/resend-verification', status_code=202)
def resend_verification(payload: ResendRequest, request: Request, background: BackgroundTasks, db: DB, settings: Config, mailer: Mail):
    return resend_code(payload, request, background, db, settings, mailer, 'registration')


@router.post('/resend-reset', status_code=202)
def resend_reset(payload: ResendRequest, request: Request, background: BackgroundTasks, db: DB, settings: Config, mailer: Mail):
    return resend_code(payload, request, background, db, settings, mailer, 'password_reset')


@router.post('/forgot-password', status_code=202)
def forgot_password(payload: EmailRequest, request: Request, background: BackgroundTasks, db: DB, settings: Config, mailer: Mail):
    throttle(request, db, settings, payload.email)
    identifier = secrets.token_urlsafe(32)
    user = db.scalar(select(User).where(User.email == payload.email, User.is_active.is_(True)))
    if user:
        row, code = new_challenge(db, settings, user.email, 'password_reset', user_id=user.id)
        identifier = row.id
        db.commit()
        background.add_task(deliver_code, mailer, user.email, code, 'password_reset')
    return {'message': CODE_MESSAGE, 'challenge_id': identifier}


@router.post('/reset-password')
def reset_password(payload: ResetRequest, request: Request, background: BackgroundTasks, db: DB, settings: Config, mailer: Mail):
    row = db.get(EmailChallenge, payload.challenge_id)
    throttle(request, db, settings, row.email if row else payload.challenge_id)
    row = consume_code(db, settings, payload, 'password_reset')
    user = db.get(User, row.user_id) if row.user_id else None
    if not user or not user.is_active or user.email != row.email:
        db.commit()
        raise HTTPException(400, CODE_FAILURE)
    user.password_hash = hasher.hash(payload.new_password)
    user.email_verified_at = utc_now()
    db.flush()  # Serialize password changes against login's conditional user update.
    db.execute(update(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None)).values(revoked_at=utc_now()))
    invalidate_challenges(db, user.email)
    db.commit()
    background.add_task(deliver_password_changed, mailer, user.email)
    return {'message': 'Your password has been updated. Please sign in with your new password.'}


@router.post('/login')
def login(payload: Credentials, request: Request, response: Response, db: DB, settings: Config):
    throttle(request, db, settings, payload.email)
    user = db.scalar(select(User).where(User.email == payload.email))
    try:
        valid = hasher.verify(user.password_hash if user else DUMMY_HASH, payload.password)
    except (VerificationError, InvalidHashError):
        valid = False
    if not valid or not user or not user.is_active:
        raise HTTPException(401, 'Email or password is incorrect')
    if user.email_verified_at is None:
        raise HTTPException(403, 'Please verify your email using Forgot password before signing in.')
    old_hash = user.password_hash
    new_hash = hasher.hash(payload.password) if hasher.check_needs_rehash(old_hash) else old_hash
    # Prevent a login using an old password from racing a completed reset.
    locked = db.execute(update(User).where(User.id == user.id, User.password_hash == old_hash,
        User.is_active.is_(True), User.email_verified_at.is_not(None)).values(password_hash=new_hash))
    if locked.rowcount != 1:
        db.rollback()
        raise HTTPException(401, 'Email or password is incorrect')
    previous = session_for(request, db, settings)
    if previous:
        previous.revoked_at = utc_now()
    token = issue_session(response, db, settings, user.id)
    db.commit()
    return {'user': user_read(user), 'csrf_token': token}


@router.get('/me')
def me(user: Annotated[User, Depends(get_current_user)]):
    return user_read(user)


@router.post('/logout')
def logout(request: Request, response: Response, db: DB, settings: Config):
    row = session_for(request, db, settings)
    if row:
        row.revoked_at = utc_now()
        db.commit()
    response.delete_cookie(cookie_name(settings), path='/', secure=settings.cookie_secure,
                           httponly=True, samesite=settings.cookie_samesite)
    return {'message': 'Signed out'}
