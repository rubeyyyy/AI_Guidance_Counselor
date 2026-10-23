from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Student(Base):
    """Student identity and one current, schema-validated assessment snapshot.

    assessment_answers is {} until submission. API writes use Assessment's JSON
    serialization and replace the entire object so SQLAlchemy detects changes.
    Keep the existing column layout to preserve scaffold databases.
    """
    __tablename__ = "students"

    user = relationship("User", back_populates="student", uselist=False)

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    assessment_answers: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict,
        doc="Seven typed questionnaire sections; an empty object means not submitted",
    )
    # SQLite stores naive timestamps; this column always represents UTC.
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
