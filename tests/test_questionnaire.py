import pytest
from sqlalchemy.orm import Session

from app import main
from app.services.questionnaire import seed_sample
from tests.test_students import client  # noqa: F401


def setup_assessment(client):
    student = client.post("/students", json={}).json()["id"]
    questions = client.get("/questionnaires/sample-initial-v1/questions").json()
    return f"/students/{student}/assessments/sample-initial-v1", questions


def test_partial_update_resume_profile(client):
    url, questions = setup_assessment(client)
    assert [q["display_order"] for q in questions] == [1, 2, 3, 4]
    assert client.get(url + "/answers").json() == []
    empty = client.get(url + "/profile").json()
    assert empty["is_sample"] is True
    assert all(f["value"] is None for f in empty["fields"])
    assert empty["progress"]["is_complete"] is False
    answer_url = url + f"/answers/{questions[0]['id']}"
    assert client.put(answer_url, json={"value": "First"}).status_code == 200
    assert client.put(answer_url, json={"value": "Updated"}).status_code == 200
    # Each request uses a fresh session: resume returns persisted answers.
    assert client.get(url + "/answers").json() == [{"question_id": questions[0]["id"], "value": "Updated"}]
    progress = client.get(url + "/progress").json()
    assert progress["completion_percent"] == 25
    assert progress["answered_required_questions"] == 1
    assert client.put(url + f"/answers/{questions[1]['id']}", json={"value": 0}).status_code == 200
    assert client.get(url + "/progress").json()["is_complete"] is True
    profile = client.get(url + "/profile").json()
    assert [f["value"] for f in profile["fields"]] == ["Updated", 0, None, None]
    assert client.put(answer_url, json={"value": None}).status_code == 200
    assert client.get(url + "/progress").json()["is_complete"] is False
    other, _ = setup_assessment(client)
    assert client.get(other + "/answers").json() == []


@pytest.mark.parametrize("index,value", [
    (0, 12), (0, "  "), (1, "12"), (1, True), (1, []),
    (2, "unknown"), (2, ["Sample A"]), (3, "Sample A"),
    (3, []), (3, ["unknown"]), (3, ["Sample A", "Sample A"]),
])
def test_validation_preserves_answer(client, index, value):
    url, questions = setup_assessment(client)
    valid = ["text", 2.5, "Sample A", ["Sample A", "Sample B"]][index]
    endpoint = url + f"/answers/{questions[index]['id']}"
    assert client.put(endpoint, json={"value": valid}).status_code == 200
    assert client.put(endpoint, json={"value": value}).status_code == 422
    assert client.get(url + "/answers").json()[0]["value"] == valid
    assert client.put(endpoint, json={"value": valid, "unknown": 1}).status_code == 422
    assert client.put(endpoint, json={}).status_code == 422


def test_missing_resources_and_idempotent_seed(client):
    url, questions = setup_assessment(client)
    assert client.get("/questionnaires/missing/questions").status_code == 404
    assert client.get("/students/999/assessments/sample-initial-v1/profile").status_code == 404
    assert client.get(url.replace("sample-initial-v1", "missing") + "/answers").status_code == 404
    assert client.put(url + "/answers/999", json={"value": "x"}).status_code == 404
    with Session(main.engine) as session:
        seed_sample(session)
    assert client.get("/questionnaires/sample-initial-v1/questions").json() == questions
