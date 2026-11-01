from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class PathwayPlan(Base):
    __tablename__ = 'pathway_plans'
    student_id: Mapped[int] = mapped_column(ForeignKey('students.id'), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
