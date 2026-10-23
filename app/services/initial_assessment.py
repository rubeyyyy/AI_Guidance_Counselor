"""The supplied questionnaire, using the existing Assessment schema's choices/types."""
from typing import get_args

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.questionnaire import Question, StudentAnswer
from app.models.student import Student
from app.schemas.assessment import Assessment
from app.schemas.questionnaire import QuestionnaireDefinition

QUESTIONNAIRE_ID = "initial-v1"
# Prompt wording follows the fields documented for the supplied questionnaire.
PROMPTS = {
    "name": "What is your name?",
    "age": "How old are you?",
    "grade": "What grade or year are you in?",
    "city": "What city do you live in?",
    "current_program": "What program are you currently studying?",
    "gpa": "What is your current GPA?",
    "short_term_goal": "What is your short-term career or education goal?",
    "short_term_timeline": "When would you like to achieve your short-term goal?",
    "long_term_aspirations": "What are your long-term career aspirations?",
    "long_term_timeline": "When would you like to achieve your long-term goal?",
    "confidence": "How confident do you feel about your career direction?",
    "knows_tutoring_resources": "Do you know where to find tutoring resources?",
    "knows_how_to_find_internship": "Do you know how to find an internship?",
    "knows_job_training_resources": "Do you know where to find job training resources?",
    "has_talked_to_career_adult": "Have you talked to an adult about your career plans?",
    "knows_required_education": "Do you know what education your desired career requires?",
    "career_interest_reason": "Why are you interested in your chosen career?",
    "primary_motivator": "What motivates your career choice the most?",
    "other_motivator": "What other factor motivates your career choice?",
    "soft_skills": "Which soft skills do you have? Select all that apply.",
    "technical_skills_raw": "What technical skills do you have? Include your proficiency if known.",
    "related_experiences": "What experiences relate to your career interests?",
    "certifications": "Do you have any certifications?",
    "clubs_competitions_projects": "What clubs, competitions, or projects have you participated in?",
    "socioeconomic_factors": "Which circumstances describe your situation? Select all that apply.",
    "has_personal_laptop": "Do you have a personal laptop?",
    "has_reliable_internet": "Do you have reliable internet access?",
    "biggest_obstacle": "What is the biggest obstacle to achieving your goals?",
    "other_obstacle": "What other obstacle are you facing?",
    "weekly_learning_hours": "How many hours per week can you dedicate to learning?",
    "learning_preferences": "How do you prefer to learn? Select all that apply.",
}
CONDITIONS = {"other_motivator": {"primary_motivator": "Other"},
              "other_obstacle": {"biggest_obstacle": "Other"}}
BOOLEANS = {"has_personal_laptop", "has_reliable_internet"}


def schema_fields():
    for section, info in Assessment.model_fields.items():
        section_type = info.annotation
        if not isinstance(section_type, type):
            section_type = next(t for t in get_args(section_type) if t is not type(None))
        for key, field in section_type.model_fields.items():
            if key in PROMPTS:
                yield section, key, field


def definition() -> QuestionnaireDefinition:
    questions = []
    for index, (_, key, field) in enumerate(schema_fields(), 1):
        schema = TypeAdapter(field.rebuild_annotation()).json_schema()
        if "anyOf" in schema:
            schema = next(s for s in schema["anyOf"] if s.get("type") != "null")
        options = schema.get("enum", schema.get("items", {}).get("enum", []))
        if key in BOOLEANS:
            kind, options = "single-choice", ["Yes", "No"]
        elif schema.get("type") == "array":
            kind = "multiple-choice"
        elif options:
            kind = "single-choice"
        elif schema.get("type") in ("number", "integer"):
            kind = "number"
        else:
            kind = "text"
        questions.append(dict(key=key, prompt=PROMPTS[key], response_type=kind,
                              required=field.is_required(), display_order=index, options=options))
    return QuestionnaireDefinition(id=QUESTIONNAIRE_ID, title="PathBridge AI Initial Assessment",
                                   is_sample=False, questions=questions)


def validate_answer(key: str, value):
    if value is None:
        return None  # Drafts can be cleared and resumed.
    field = next(field for _, name, field in schema_fields() if name == key)
    if key in BOOLEANS:
        if value not in ("Yes", "No"):
            raise ValueError("Choose Yes or No")
        return value
    return TypeAdapter(field.rebuild_annotation()).validate_python(value)


def import_snapshot(db: Session, student: Student, overwrite: bool = False):
    """Carry forward existing real assessments without replacing individually saved work."""
    if not student.assessment_answers:
        return
    try:
        snapshot = Assessment.model_validate(student.assessment_answers).model_dump()
    except ValueError:
        return  # Preserve older/untyped data; never guess or delete it.
    questions = list(db.scalars(select(Question).where(Question.questionnaire_id == QUESTIONNAIRE_ID)))
    saved = {a.question_id: a for a in db.scalars(select(StudentAnswer).where(StudentAnswer.student_id == student.id))}
    values = {key: (snapshot.get(section) or {}).get(key) for section, key, _ in schema_fields()}
    if not values.get("technical_skills_raw"):
        skills = snapshot["skills"].get("technical_skills") or []
        values["technical_skills_raw"] = "; ".join(s["name"] + (f" ({s['proficiency']})" if s["proficiency"] else "") for s in skills) or None
    for question in questions:
        value = values[question.key]
        if question.key in BOOLEANS and value is not None:
            value = "Yes" if value else "No"
        if question.id not in saved:
            db.add(StudentAnswer(student_id=student.id, question_id=question.id, value=value))
        elif overwrite:
            saved[question.id].value = value


def seed_initial(db: Session):
    from app.services.questionnaire import load_questionnaire

    load_questionnaire(db, definition())
    for student in db.scalars(select(Student)):
        import_snapshot(db, student)
    db.commit()
