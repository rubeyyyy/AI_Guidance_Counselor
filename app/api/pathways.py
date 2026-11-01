from typing import Annotated, Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from app.api.auth import own_student
from app.api.students import Database, StudentId
from app.services import pathways
from app.services.llm import LLMService, get_llm
from app.core.config import Settings, get_settings

LLM = Annotated[LLMService, Depends(get_llm)]
Configuration = Annotated[Settings, Depends(get_settings)]

router = APIRouter(prefix='/students', tags=['Pathways'], dependencies=[Depends(own_student)])


class StepUpdate(BaseModel):
    status: Literal['not_started', 'in_progress', 'completed']
    notes: str = Field(default='', max_length=2000)


@router.get('/{student_id}/pathway')
def get_pathway(student_id: StudentId, db: Database):
    return pathways.read(db, student_id)


@router.post('/{student_id}/pathway/generate')
def generate_pathway(student_id: StudentId, db: Database, llm: LLM, settings: Configuration):
    return pathways.generate(db, student_id, llm, settings)


@router.post('/{student_id}/pathway/rebuild')
def rebuild_pathway(student_id: StudentId, db: Database, llm: LLM, settings: Configuration):
    return pathways.generate(db, student_id, llm, settings, replace=True)


@router.put('/{student_id}/pathway/steps/{step_id}')
def update_step(student_id: StudentId, step_id: str, payload: StepUpdate, db: Database):
    return pathways.update(db, student_id, step_id, payload.status, payload.notes)
