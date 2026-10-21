from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.knowledge_base import router as knowledge_router
from app.api.questionnaire import router as questionnaire_router
from app.api.health import router as health_router
from app.api.students import router as students_router
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
app.add_middleware(
    CORSMiddleware, allow_origins=get_settings().cors_origins,
    allow_methods=["GET", "POST", "PUT"], allow_headers=["Content-Type"],
    allow_credentials=False,
)
app.include_router(health_router)
app.include_router(students_router)

app.include_router(questionnaire_router)
app.include_router(chat_router)
app.include_router(knowledge_router)
