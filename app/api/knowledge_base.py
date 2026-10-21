from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.services.knowledge import knowledge_status

router = APIRouter(prefix="/knowledge-base", tags=["knowledge base"])


class KnowledgeStatus(BaseModel):
    enabled: bool
    initialized: bool
    documents: int
    chunks: int
    state: str


@router.get("/status", response_model=KnowledgeStatus)
def status(settings: Annotated[Settings, Depends(get_settings)]):
    try:
        return knowledge_status(settings)
    except Exception:
        return {"enabled": settings.rag_enabled, "initialized": False,
                "documents": 0, "chunks": 0, "state": "unavailable"}
