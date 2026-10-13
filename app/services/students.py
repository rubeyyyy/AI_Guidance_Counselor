from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Student
from app.schemas.assessment import Assessment
from app.schemas.student import StudentCreate


def find_student(student_id: int, db: Session) -> Student:
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    return student


def create_student(payload: StudentCreate, db: Session) -> Student:
    student = Student(**payload.model_dump())
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


def replace_assessment(student_id: int, payload: Assessment, db: Session) -> Assessment:
    student = find_student(student_id, db)
    student.assessment_answers = payload.model_dump(mode="json")
    db.commit()
    return payload
