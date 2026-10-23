from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.questionnaire import Question, Questionnaire, StudentAnswer
from app.schemas.questionnaire import AnswerWrite, Progress, QuestionnaireDefinition, StudentProfile
from app.services.students import find_student
from app.services.initial_assessment import CONDITIONS, QUESTIONNAIRE_ID, validate_answer
from app.services.short_assessment import QUESTIONNAIRE_ID as SHORT_ID, validate_answer as validate_short_answer


def load_questionnaire(db: Session, definition: QuestionnaireDefinition) -> None:
    """Import once. Use a new version ID for changed questions to preserve answers."""
    if db.get(Questionnaire, definition.id) is not None:
        return
    db.add(Questionnaire(**definition.model_dump(exclude={"questions"})))
    db.flush()
    for question in definition.questions:
        db.add(Question(questionnaire_id=definition.id, **question.model_dump()))
    db.commit()


def seed_sample(db: Session) -> None:
    path = Path(__file__).resolve().parents[1] / "fixtures/sample_questionnaire.json"
    load_questionnaire(db, QuestionnaireDefinition.model_validate_json(path.read_text()))


def questions(db: Session, questionnaire_id: str):
    if db.get(Questionnaire, questionnaire_id) is None:
        raise HTTPException(404, "Questionnaire not found")
    definitions = list(db.scalars(select(Question).where(Question.questionnaire_id == questionnaire_id)
                                 .order_by(Question.display_order, Question.id)))
    for question in definitions:
        question.required_when = CONDITIONS.get(question.key) if questionnaire_id == QUESTIONNAIRE_ID else None
    return definitions


def answers(db: Session, student_id: int, questionnaire_id: str):
    find_student(student_id, db)
    definitions = questions(db, questionnaire_id)
    ids = [q.id for q in definitions]
    return list(db.scalars(select(StudentAnswer).join(Question).where(
        StudentAnswer.student_id == student_id, StudentAnswer.question_id.in_(ids)
    ).order_by(Question.display_order, Question.id)))


def save_answer(db: Session, student_id: int, questionnaire_id: str, question_id: int, payload: AnswerWrite):
    find_student(student_id, db)
    question = next((q for q in questions(db, questionnaire_id) if q.id == question_id), None)
    if question is None:
        raise HTTPException(404, "Question not found in questionnaire")
    value = payload.value
    if questionnaire_id == SHORT_ID:
        try:
            value = validate_short_answer(question.key, value)
        except ValueError:
            raise HTTPException(422, "Answer does not match the questionnaire's allowed values or numeric limits") from None
    if questionnaire_id == QUESTIONNAIRE_ID:
        condition = CONDITIONS.get(question.key)
        if condition and value is not None:
            definitions = questions(db, questionnaire_id)
            for key, expected in condition.items():
                parent = next(q for q in definitions if q.key == key)
                parent_answer = db.scalar(select(StudentAnswer).where(
                    StudentAnswer.student_id == student_id, StudentAnswer.question_id == parent.id))
                if parent_answer is None or parent_answer.value != expected:
                    raise HTTPException(422, "This follow-up question applies only when Other is selected")
        try:
            value = validate_answer(question.key, value)
        except ValueError:
            raise HTTPException(422, "Answer does not match the questionnaire's allowed values or numeric limits") from None
    # Null clears an answer, including required ones, so drafts remain resumable.
    if value is not None:
        valid = False
        if question.response_type == "text":
            valid = isinstance(value, str) and bool(value.strip())
        elif question.response_type == "number":
            valid = type(value) in (int, float)
        elif question.response_type == "single-choice":
            valid = isinstance(value, str) and value in question.options
        elif question.response_type == "multiple-choice":
            valid = (isinstance(value, list) and bool(value) and len(set(value)) == len(value)
                     and all(v in question.options for v in value))
        if not valid:
            raise HTTPException(422, "Answer does not match question type or allowed options")
    answer = db.scalar(select(StudentAnswer).where(
        StudentAnswer.student_id == student_id, StudentAnswer.question_id == question_id))
    if answer is None:
        answer = StudentAnswer(student_id=student_id, question_id=question_id, value=value)
        db.add(answer)
    else:
        answer.value = value
    if questionnaire_id == QUESTIONNAIRE_ID:
        for child, condition in CONDITIONS.items():
            if question.key in condition and value != condition[question.key]:
                child_question = next(q for q in questions(db, questionnaire_id) if q.key == child)
                child_answer = db.scalar(select(StudentAnswer).where(
                    StudentAnswer.student_id == student_id, StudentAnswer.question_id == child_question.id))
                if child_answer is not None:
                    child_answer.value = None
    db.commit()
    db.refresh(answer)
    return answer


def profile(db: Session, student_id: int, questionnaire_id: str) -> StudentProfile:
    student = find_student(student_id, db)
    definitions = questions(db, questionnaire_id)
    saved = {a.question_id: a.value for a in answers(db, student_id, questionnaire_id)}
    by_key = {q.key: saved.get(q.id) for q in definitions}
    def applies(q):
        condition = getattr(q, "required_when", None)
        return not condition or all(by_key.get(key) == value for key, value in condition.items())
    definitions = [q for q in definitions if applies(q)]
    def required(q):
        return q.required or bool(getattr(q, "required_when", None))
    answered = sum(saved.get(q.id) is not None for q in definitions)
    required_count = sum(required(q) for q in definitions)
    answered_required = sum(required(q) and saved.get(q.id) is not None for q in definitions)
    return StudentProfile(
        student_id=student.id, display_name=student.display_name,
        questionnaire_id=questionnaire_id, is_sample=db.get(Questionnaire, questionnaire_id).is_sample,
        fields=[{"key": q.key, "question_id": q.id, "value": saved.get(q.id)} for q in definitions],
        progress=Progress(total_questions=len(definitions), answered_questions=answered,
                          required_questions=required_count, answered_required_questions=answered_required,
                          completion_percent=round(100 * answered / len(definitions), 2) if definitions else 0,
                          is_complete=answered_required == required_count),
    )
