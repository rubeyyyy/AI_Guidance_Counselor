from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Student
from app.services import students as service
from app.services.students import find_student
from app.schemas.assessment import Assessment
from app.schemas.student import StudentCreate, StudentRead

router = APIRouter(prefix="/students", tags=["students"])
Database = Annotated[Session, Depends(get_db)]
StudentId = Annotated[int, Path(gt=0)]


@router.post("", response_model=StudentRead, status_code=status.HTTP_201_CREATED)
def create_student(payload: StudentCreate, response: Response, db: Database) -> Student:
    student = service.create_student(payload, db)
    response.headers["Location"] = f"/students/{student.id}"
    return student


@router.get("/{student_id}", response_model=StudentRead)
def get_student(student_id: StudentId, db: Database) -> Student:
    return find_student(student_id, db)


@router.get("/{student_id}/assessment", response_model=Assessment)
def get_assessment(student_id: StudentId, db: Database) -> Assessment:
    student = find_student(student_id, db)
    if not student.assessment_answers:
        raise HTTPException(status_code=404, detail="Assessment not submitted")
    try:
        return Assessment.model_validate(student.assessment_answers)
    except ValidationError:
        # Preserve any untyped data written with the earlier scaffold; do not
        # silently reinterpret it as a completed questionnaire or expose it.
        raise HTTPException(
            status_code=409,
            detail="Stored assessment uses an older format; submit a complete assessment",
        ) from None


@router.put("/{student_id}/assessment", response_model=Assessment)
def replace_assessment(student_id: StudentId, payload: Assessment, db: Database) -> Assessment:
    return service.replace_assessment(student_id, payload, db)
