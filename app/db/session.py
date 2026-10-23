from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def build_engine(database_url: str) -> Engine:
    connect_args = {}
    if make_url(database_url).get_backend_name() == "sqlite":
        # FastAPI may use the same request session across worker threads.
        connect_args["check_same_thread"] = False
    result = create_engine(database_url, connect_args=connect_args)
    if make_url(database_url).get_backend_name() == "sqlite":
        @event.listens_for(result, "connect")
        def enable_foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")
    return result


engine = build_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(bind: Engine) -> None:
    # Register all models before seeding questionnaire definitions.
    from app.models import Student  # noqa: F401

    # Schema changes are explicit Alembic operations; startup only seeds definitions.
    from alembic.migration import MigrationContext
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    with bind.connect() as connection:
        revision = MigrationContext.configure(connection).get_current_revision()
    from app.core.config import PROJECT_ROOT
    head = ScriptDirectory.from_config(Config(str(PROJECT_ROOT / "alembic.ini"))).get_current_head()
    if revision != head:
        raise RuntimeError("Database migration required: run python -m alembic upgrade head")
    from app.services.questionnaire import seed_sample
    from app.services.initial_assessment import seed_initial
    from app.services.short_assessment import seed_short

    with Session(bind) as session:
        seed_sample(session)
        seed_initial(session)
        seed_short(session)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
