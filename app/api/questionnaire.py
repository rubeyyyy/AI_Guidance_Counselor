from fastapi import APIRouter

from app.api.students import Database, StudentId
from app.schemas.questionnaire import AnswerRead, AnswerWrite, Progress, QuestionRead, StudentProfile
from app.services import questionnaire as service

router = APIRouter(tags=["initial assessment"])


@router.get("/questionnaires/{questionnaire_id}/questions", response_model=list[QuestionRead])
def get_questions(questionnaire_id: str, db: Database):
    return service.questions(db, questionnaire_id)


@router.put("/students/{student_id}/assessments/{questionnaire_id}/answers/{question_id}", response_model=AnswerRead)
def save_answer(student_id: StudentId, questionnaire_id: str, question_id: StudentId,
                payload: AnswerWrite, db: Database):
    return service.save_answer(db, student_id, questionnaire_id, question_id, payload)


@router.get("/students/{student_id}/assessments/{questionnaire_id}/answers", response_model=list[AnswerRead])
def get_answers(student_id: StudentId, questionnaire_id: str, db: Database):
    return service.answers(db, student_id, questionnaire_id)


@router.get("/students/{student_id}/assessments/{questionnaire_id}/progress", response_model=Progress)
def get_progress(student_id: StudentId, questionnaire_id: str, db: Database):
    return service.profile(db, student_id, questionnaire_id).progress


@router.get("/students/{student_id}/assessments/{questionnaire_id}/profile", response_model=StudentProfile)
def get_profile(student_id: StudentId, questionnaire_id: str, db: Database):
    return service.profile(db, student_id, questionnaire_id)
