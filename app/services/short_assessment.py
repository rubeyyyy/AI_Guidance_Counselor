"""Twenty-question revision; the original published questionnaire stays intact."""
from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.questionnaire import Question, StudentAnswer
from app.models.student import Student
from app.schemas.assessment import Motivator, Obstacle, Selections
from app.schemas.questionnaire import QuestionnaireDefinition
from app.services.initial_assessment import QUESTIONNAIRE_ID as ORIGINAL_ID
from app.services.initial_assessment import definition as original_definition, validate_answer as original_validation

QUESTIONNAIRE_ID = "initial-v2"
KEYS = [
    "grade", "current_program", "gpa", "short_term_goal", "short_term_timeline",
    "long_term_aspirations", "confidence", "knows_required_education",
    "career_interest_reason", "primary_motivator", "soft_skills", "technical_skills_raw",
    "related_experiences", "certifications", "socioeconomic_factors",
    "has_personal_laptop", "has_reliable_internet", "biggest_obstacle",
    "weekly_learning_hours", "learning_preferences",
]
REQUIRED = {"grade", "short_term_goal", "long_term_aspirations", "soft_skills", "learning_preferences"}
MULTI = {"primary_motivator": Motivator, "biggest_obstacle": Obstacle}


def definition() -> QuestionnaireDefinition:
    originals = {q.key: q for q in original_definition().questions}
    questions = []
    for order, key in enumerate(KEYS, 1):
        question = originals[key].model_copy(update={"display_order": order, "required": key in REQUIRED})
        if key in MULTI:
            question.response_type = "multiple-choice"
            question.prompt = ("What motivates your career choices? Select all that apply."
                               if key == "primary_motivator" else
                               "What obstacles make it harder to achieve your goals? Select all that apply.")
        questions.append(question)
    return QuestionnaireDefinition(id=QUESTIONNAIRE_ID, title="PathBridge AI Initial Assessment",
                                   is_sample=False, questions=questions)


def validate_answer(key: str, value):
    if key in MULTI and value is not None:
        return TypeAdapter(Selections[MULTI[key]]).validate_python(value)
    return original_validation(key, value)


def carry_forward(db: Session, student_id: int, overwrite: bool = False):
    """Copy retained fields once; wrap old single choices without changing originals."""
    originals = dict(db.execute(select(Question.id, Question.key).where(Question.questionnaire_id == ORIGINAL_ID)).all())
    source = {originals[a.question_id]: a.value for a in db.scalars(select(StudentAnswer).where(
        StudentAnswer.student_id == student_id, StudentAnswer.question_id.in_(originals)))}
    questions = list(db.scalars(select(Question).where(Question.questionnaire_id == QUESTIONNAIRE_ID)))
    saved = {a.question_id: a for a in db.scalars(select(StudentAnswer).where(
        StudentAnswer.student_id == student_id, StudentAnswer.question_id.in_([q.id for q in questions])))}
    for question in questions:
        if question.key not in source:
            continue
        value = source[question.key]
        if question.key in MULTI and isinstance(value, str):
            value = [value]
        if question.id not in saved:
            db.add(StudentAnswer(student_id=student_id, question_id=question.id, value=value))
        elif overwrite:
            saved[question.id].value = value


def seed_short(db: Session):
    from app.services.questionnaire import load_questionnaire

    load_questionnaire(db, definition())
    for student_id in db.scalars(select(Student.id)):
        carry_forward(db, student_id)
    db.commit()
