"""Question definitions and answers are independent of the legacy snapshot."""
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Questionnaire(Base):
    __tablename__ = "questionnaires"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)


class Question(Base):
    __tablename__ = "assessment_questions"
    __table_args__ = (UniqueConstraint("questionnaire_id", "key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    questionnaire_id: Mapped[str] = mapped_column(ForeignKey("questionnaires.id"))
    key: Mapped[str] = mapped_column(String(100))
    prompt: Mapped[str] = mapped_column(String)
    response_type: Mapped[str] = mapped_column(String(30))
    required: Mapped[bool] = mapped_column(Boolean)
    display_order: Mapped[int] = mapped_column()
    options: Mapped[list[str]] = mapped_column(JSON, default=list)


class StudentAnswer(Base):
    __tablename__ = "student_answers"
    __table_args__ = (UniqueConstraint("student_id", "question_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    question_id: Mapped[int] = mapped_column(ForeignKey("assessment_questions.id"))
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
