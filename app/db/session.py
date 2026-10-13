from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.base import Base


def build_engine(database_url: str) -> Engine:
    connect_args = {}
    if make_url(database_url).get_backend_name() == "sqlite":
        # FastAPI may use the same request session across worker threads.
        connect_args["check_same_thread"] = False
    return create_engine(database_url, connect_args=connect_args)


engine = build_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(bind: Engine) -> None:
    # Register model metadata before creating tables.
    from app.models import Student  # noqa: F401

    Base.metadata.create_all(bind=bind)
    from app.services.questionnaire import seed_sample

    with Session(bind) as session:
        seed_sample(session)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
