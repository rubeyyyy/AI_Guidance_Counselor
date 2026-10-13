from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    questionnaire_id: Mapped[str] = mapped_column(ForeignKey("questionnaires.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')"),
        CheckConstraint("status IN ('pending', 'completed', 'failed')"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="completed")
    # Associate a reply with its exact turn, even if requests overlap.
    reply_to_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversation_messages.id"), nullable=True, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
