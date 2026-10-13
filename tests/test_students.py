import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import main
from app.db.session import build_engine, get_db
from app.models import Student


@pytest.fixture
def payload():
    return json.loads(
        (Path(__file__).resolve().parents[1] / "examples/assessment.json").read_text()
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = build_engine(f"sqlite:///{tmp_path / 'students.db'}")
    monkeypatch.setattr(main, "engine", engine)

    def test_db():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[get_db] = test_db
    try:
        with TestClient(main.app) as test_client:
            yield test_client
    finally:
        main.app.dependency_overrides.clear()


def test_student_and_assessment_lifecycle(client, payload):
    created = client.post("/students", json={"display_name": " Sample "})
    assert created.status_code == 201
    student_id = created.json()["id"]
    student_url = f"/students/{student_id}"
    assessment_url = f"{student_url}/assessment"
    assert created.headers["location"] == student_url
    assert created.json()["display_name"] == "Sample"
    assert client.get(student_url).json() == created.json()
    assert client.get(assessment_url).status_code == 404

    submitted = client.put(assessment_url, json=payload)
    assert submitted.status_code == 200
    assert submitted.json() == payload
    assert client.get(assessment_url).json() == payload

    payload["basic_information"]["gpa"] = 4.5
    payload["skills"]["technical_skills"] = [{"name": "Python"}]
    payload.pop("experience")
    replaced = client.put(assessment_url, json=payload)
    assert replaced.status_code == 200
    stored = client.get(assessment_url).json()
    assert stored["basic_information"]["gpa"] == 4.5
    assert stored["skills"]["technical_skills"] == [{"name": "Python", "proficiency": None}]
    assert stored["experience"] is None  # PUT replaces, rather than merges.
    assert client.put(assessment_url, json=payload).json() == stored

    # Another student's profile remains independent.
    second = client.post("/students", json={}).json()
    assert second["id"] != student_id
    assert client.get(f"/students/{second['id']}/assessment").status_code == 404


def test_missing_students(client, payload):
    assert client.get("/students/999").status_code == 404
    assert client.get("/students/999/assessment").status_code == 404
    assert client.put("/students/999/assessment", json=payload).status_code == 404
    assert client.get("/students/0").status_code == 422
    assert client.get("/students/not-an-id").status_code == 422


@pytest.mark.parametrize(("section", "field", "value"), [
    ("basic_information", "name", "   "),
    ("basic_information", "age", 16.5),
    ("basic_information", "age", True),
    ("basic_information", "gpa", -1),
    ("basic_information", "gpa", "3.5"),
    ("career_goals", "short_term_timeline", "1-3 Years"),
    ("career_goals", "long_term_timeline", "3-6 Month"),
    ("career_goals", "confidence", "Unknown"),
    ("career_awareness", "knows_tutoring_resources", True),
    ("motivation", "other_motivator", None),
    ("motivation", "primary_motivator", "Passion/interest"),
    ("skills", "soft_skills", []),
    ("skills", "soft_skills", ["Teamwork", "Teamwork"]),
    ("skills", "technical_skills", [{"name": "Python", "proficiency": "Expert"}]),
    ("support_resources", "has_personal_laptop", "No"),
    ("support_resources", "weekly_learning_hours", 169),
    ("support_resources", "weekly_learning_hours", -1),
    ("support_resources", "learning_preferences", []),
    ("support_resources", "socioeconomic_factors", ["Unknown"]),
    ("support_resources", "other_obstacle", " "),
    ("support_resources", "biggest_obstacle", "Time constraints"),
])
def test_invalid_answers_do_not_overwrite(client, payload, section, field, value):
    student = client.post("/students", json={}).json()
    url = f"/students/{student['id']}/assessment"
    assert client.put(url, json=payload).status_code == 200
    original = client.get(url).json()
    payload[section][field] = value
    assert client.put(url, json=payload).status_code == 422
    assert client.get(url).json() == original


def test_missing_and_optional_answers(client, payload):
    student_id = client.post("/students", json={}).json()["id"]
    url = f"/students/{student_id}/assessment"
    assert client.put(url, json={}).status_code == 422
    payload["skills"].pop("technical_skills")
    payload["skills"].pop("technical_skills_raw")
    payload["experience"] = {"certifications": "  "}
    response = client.put(url, json=payload)
    assert response.status_code == 200
    assert response.json()["skills"]["technical_skills"] is None
    assert response.json()["experience"]["certifications"] is None
    del payload["career_awareness"]["knows_required_education"]
    assert client.put(url, json=payload).status_code == 422


def test_unknown_fields_and_unvalidated_creation_rejected(client, payload):
    assert client.post("/students", json={"assessment_answers": payload}).status_code == 422
    student_id = client.post("/students", json={}).json()["id"]
    payload["skills"]["unknown"] = "must not silently disappear"
    assert client.put(f"/students/{student_id}/assessment", json=payload).status_code == 422


def test_legacy_assessment_is_preserved(client):
    with Session(main.engine) as session:
        student = Student(assessment_answers={"old_question": "old answer"})
        session.add(student)
        session.commit()
        student_id = student.id
    assert client.get(f"/students/{student_id}").status_code == 200
    assert client.get(f"/students/{student_id}/assessment").status_code == 409
    with Session(main.engine) as session:
        assert session.get(Student, student_id).assessment_answers == {"old_question": "old answer"}
