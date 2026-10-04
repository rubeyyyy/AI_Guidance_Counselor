from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import get_settings
from app.db.session import engine, init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        init_db(engine)
        yield
    finally:
        engine.dispose()


app = FastAPI(title=get_settings().app_name, lifespan=lifespan)
app.include_router(health_router)
