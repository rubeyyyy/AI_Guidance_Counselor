from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.auth import own_student
from app.api.students import Database, StudentId
from app.core.config import Settings, get_settings
from app.schemas.chat import ChatErrorResponse, ChatRequest, ChatResponse, ConversationDetail, ConversationRead
from app.services import guidance
from app.services.llm import LLMService, get_llm
from app.services.retrieval import RetrievalService, get_retrieval

router = APIRouter(prefix="/students", tags=["AI guidance"], dependencies=[Depends(own_student)])
LLM = Annotated[LLMService, Depends(get_llm)]
Configuration = Annotated[Settings, Depends(get_settings)]
Retrieval = Annotated[RetrievalService, Depends(get_retrieval)]


@router.post("/{student_id}/chat", response_model=ChatResponse, responses={
    502: {"model": ChatErrorResponse, "description": "Provider failed; student message saved"},
    503: {"model": ChatErrorResponse, "description": "Provider not configured; student message saved"},
})
def chat(student_id: StudentId, payload: ChatRequest, db: Database, llm: LLM,
         settings: Configuration, retrieval: Retrieval):
    return guidance.chat(db, student_id, payload, llm, settings, retrieval)


@router.get("/{student_id}/conversations", response_model=list[ConversationRead])
def list_conversations(student_id: StudentId, db: Database):
    return guidance.list_conversations(db, student_id)


@router.get("/{student_id}/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(student_id: StudentId, conversation_id: StudentId, db: Database):
    return guidance.conversation_detail(db, student_id, conversation_id)
