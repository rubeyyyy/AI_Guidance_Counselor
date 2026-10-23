from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base
from app.models.conversation import utc_now


class User(Base):
    __tablename__ = 'users'
    __table_args__ = (CheckConstraint("role IN ('student', 'counselor')"),
                      CheckConstraint("role = 'student' OR student_id IS NULL"))
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    student_id: Mapped[int | None] = mapped_column(ForeignKey('students.id'), unique=True)
    student = relationship('Student', back_populates='user')


class AuthSession(Base):
    __tablename__ = 'auth_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)


class AuthAttempt(Base):
    __tablename__ = 'auth_attempts'
    id: Mapped[int] = mapped_column(primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class EmailChallenge(Base):
    __tablename__ = 'email_challenges'
    __table_args__ = (
        CheckConstraint("purpose IN ('registration', 'password_reset')"),
        CheckConstraint('attempts >= 0'),
    )
    id: Mapped[str] = mapped_column(String(43), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), index=True)
    purpose: Mapped[str] = mapped_column(String(20))
    code_hash: Mapped[str] = mapped_column(String(64))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime)
