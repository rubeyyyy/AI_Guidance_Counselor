from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.api.auth import router as auth_router, enforce_csrf
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


app = FastAPI(title=get_settings().app_name, lifespan=lifespan, dependencies=[Depends(enforce_csrf)])
app.add_middleware(
    CORSMiddleware, allow_origins=get_settings().cors_origins,
    allow_methods=["GET", "POST", "PUT"], allow_headers=["Content-Type", "X-CSRF-Token"],
    allow_credentials=True,
)
app.include_router(health_router)
app.include_router(students_router)

app.include_router(questionnaire_router)
app.include_router(chat_router)
app.include_router(knowledge_router)

app.include_router(auth_router)

@app.middleware("http")
async def private_responses(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response

@app.exception_handler(RequestValidationError)
async def safe_validation_error(request: Request, exc: RequestValidationError):
    # FastAPI normally echoes invalid input (including passwords) in error bodies.
    return JSONResponse(status_code=422, content={"detail": [
        {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()
    ]})
