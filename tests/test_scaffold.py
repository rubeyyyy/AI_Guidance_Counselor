from datetime import timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app import main
from app.core.config import Settings
from app.db.session import build_engine
from app.models import Student
from app.schemas.student import StudentCreate, StudentRead


def test_startup_health_and_student_persistence(tmp_path, monkeypatch):
    engine = build_engine(f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setattr(main, "engine", engine)

    with TestClient(main.app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert "students" in inspect(engine).get_table_names()

        payload = StudentCreate(
            display_name=" Test Student ",
            assessment_answers={
                "gpa": 3.2,
                "laptop_access": False,
                "skills": [{"name": "Python", "proficiency": "beginner"}],
                "weekly_hours": 5,
            },
        )
        with Session(engine) as session:
            student = Student(**payload.model_dump())
            session.add(student)
            session.commit()
            student_id = student.id

        # A separate session verifies an actual database round trip.
        with Session(engine) as session:
            saved = session.get(Student, student_id)
            result = StudentRead.model_validate(saved)
            assert result.display_name == "Test Student"
            assert result.assessment_answers == payload.assessment_answers
            assert result.created_at.tzinfo == timezone.utc


def test_student_schema_validation_and_independent_defaults():
    first, second = StudentCreate(), StudentCreate()
    first.assessment_answers["weekly_hours"] = 5
    assert second.assessment_answers == {}
    invalid_inputs = [
        {"display_name": "   "},
        {"unexpected": True},
        {"assessment_answers": ["not an object"]},
    ]
    for invalid in invalid_inputs:
        with pytest.raises(ValidationError):
            StudentCreate(**invalid)


def test_environment_overrides_dotenv(tmp_path, monkeypatch):
    dotenv = tmp_path / ".env"
    dotenv.write_text("APP_NAME=From file\nDATABASE_URL=sqlite:///file.db\n")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("APP_NAME", "From environment")
    settings = Settings(_env_file=dotenv)
    assert settings.app_name == "From environment"
    assert settings.database_url == "sqlite:///file.db"
