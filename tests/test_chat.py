import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from openai import APIConnectionError, APIStatusError, APITimeoutError
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import main
from app.core.config import Settings, get_settings
from app.models.conversation import Conversation, ConversationMessage
from app.models.questionnaire import Question, StudentAnswer
from app.services import llm as llm_module
from app.services.llm import LLMError, OpenAILLMService, get_llm
from app.services.profile_context import build_profile_context
from app.services.guidance import recent_history
from tests.test_students import client  # noqa: F401


class FakeLLM:
    def __init__(self):
        self.calls = []
        self.failure = None

    def generate(self, instructions, messages):
        self.calls.append((instructions, messages))
        if self.failure:
            raise self.failure
        return "Consider an affordable introductory course and discuss your plan with a human counselor."


@pytest.fixture
def fake_llm(client, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Tests must not call the live OpenAI API")

    monkeypatch.setattr(llm_module, "OpenAI", forbidden)
    fake = FakeLLM()
    main.app.dependency_overrides[get_llm] = lambda: fake
    main.app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    return fake


def student(client, name=None):
    return client.post("/students", json={"display_name": name}).json()["id"]


def test_chat_create_resume_history_and_profile(client, fake_llm):
    sid = student(client, "Fictional Person")
    questions = client.get("/questionnaires/sample-initial-v1/questions").json()
    client.put(f"/students/{sid}/assessments/sample-initial-v1/answers/{questions[0]['id']}",
               json={"value": "I enjoy programming but have limited internet access"})
    assert client.get(f"/students/{sid}/conversations").json() == []
    first = client.post(f"/students/{sid}/chat", json={"message": "What can I explore?"})
    assert first.status_code == 200
    result = first.json()
    cid = result["conversation_id"]
    assert result["student_message"]["status"] == "completed"
    assert result["assistant_message"]["reply_to_message_id"] == result["student_message"]["id"]
    instructions, inputs = fake_llm.calls[0]
    assert "limited internet access" in instructions
    assert "Fictional Person" not in instructions
    assert '"display_name"' not in instructions and '"student_id"' not in instructions
    assert '"sample_number": null' in instructions
    assert '"is_sample": true' in instructions
    assert inputs == [{"role": "user", "content": "What can I explore?"}]

    # Refresh the saved profile for every chat request, not only at session creation.
    client.put(f"/students/{sid}/assessments/sample-initial-v1/answers/{questions[0]['id']}",
               json={"value": "I now prefer hands-on learning"})
    second = client.post(f"/students/{sid}/chat",
                         json={"message": "Suggest a next step", "conversation_id": cid})
    assert second.status_code == 200
    assert second.json()["conversation_id"] == cid
    assert "hands-on learning" in fake_llm.calls[1][0]
    assert [m["role"] for m in fake_llm.calls[1][1]] == ["user", "assistant", "user"]
    detail = client.get(f"/students/{sid}/conversations/{cid}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant", "user", "assistant"]
    assert detail["questionnaire_id"] == "sample-initial-v1"
    assert detail["created_at"].endswith("Z")
    # Verify actual persisted rows from a separate database session.
    with Session(main.engine) as db:
        assert db.get(Conversation, cid).student_id == sid
        assert len(list(db.scalars(select(ConversationMessage).where(
            ConversationMessage.conversation_id == cid)))) == 4
    another = client.post(f"/students/{sid}/chat", json={"message": "New topic"}).json()
    assert another["conversation_id"] != cid
    assert len(fake_llm.calls[-1][1]) == 1
    assert len(client.get(f"/students/{sid}/conversations").json()) == 2


def test_student_ownership_missing_and_validation(client, fake_llm):
    first, second = student(client), student(client)
    cid = client.post(f"/students/{first}/chat", json={"message": "Hello"}).json()["conversation_id"]
    calls = len(fake_llm.calls)
    assert client.get(f"/students/{second}/conversations").json() == []
    assert client.get(f"/students/{second}/conversations/{cid}").status_code == 404
    assert client.post(f"/students/{second}/chat",
                       json={"message": "Hi", "conversation_id": cid}).status_code == 404
    assert client.post(f"/students/{first}/chat",
                       json={"message": "Hi", "conversation_id": 999}).status_code == 404
    assert client.post("/students/999/chat", json={"message": "Hi"}).status_code == 404
    assert client.get("/students/999/conversations").status_code == 404
    for payload in [{}, {"message": " "}, {"message": 123}, {"message": "a" * 4001},
                    {"message": "Hi", "conversation_id": 0},
                    {"message": "Hi", "conversation_id": True},
                    {"message": "Hi", "unexpected": "field"}]:
        assert client.post(f"/students/{first}/chat", json=payload).status_code == 422
    assert len(fake_llm.calls) == calls
    assert len(client.get(f"/students/{first}/conversations/{cid}").json()["messages"]) == 2


def test_provider_failure_preserves_message_and_resume(client, fake_llm):
    sid = student(client)
    fake_llm.failure = LLMError()
    failed = client.post(f"/students/{sid}/chat", json={"message": "Help me plan"})
    assert failed.status_code == 502
    detail = failed.json()["detail"]
    cid = detail["conversation_id"]
    messages = client.get(f"/students/{sid}/conversations/{cid}").json()["messages"]
    assert len(messages) == 1
    assert messages[0]["id"] == detail["student_message_id"]
    assert messages[0]["status"] == "failed"
    assert messages[0]["content"] == "Help me plan"
    fake_llm.failure = None
    resumed = client.post(f"/students/{sid}/chat",
                          json={"message": "Help me plan again", "conversation_id": cid})
    assert resumed.status_code == 200
    assert len(fake_llm.calls[-1][1]) == 1  # Failed turns are retained locally only.
    messages = client.get(f"/students/{sid}/conversations/{cid}").json()["messages"]
    assert [m["status"] for m in messages] == ["failed", "completed", "completed"]


def test_history_limit_and_message_minimization(client, fake_llm):
    sid = student(client, "Fictional Person")
    main.app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, guidance_history_turns=1)
    cid = None
    for text in ["First topic", "Second topic", "Fictional Person: email me at sample@example.com"]:
        payload = {"message": text, "conversation_id": cid}
        response = client.post(f"/students/{sid}/chat", json=payload).json()
        cid = response["conversation_id"]
    inputs = fake_llm.calls[-1][1]
    assert len(inputs) == 3
    assert inputs[0]["content"] == "Second topic"
    assert "Fictional Person" not in inputs[-1]["content"]
    assert "sample@example.com" not in inputs[-1]["content"]
    local = client.get(f"/students/{sid}/conversations/{cid}").json()["messages"]
    assert "sample@example.com" in local[-2]["content"]


def test_context_preserves_relevant_fields_excludes_identity(client, fake_llm):
    sid = student(client, "Fictional Person")
    values = {
        "interests": "robotics", "academic_background": "studying science",
        "career_aspirations": "engineering", "skills": ["coding"],
        "learning_preferences": ["hands-on"], "resources": "library computer",
        "constraints": "limited budget", "accessibility_needs": None,
        "name": "Private Identity", "email": "private@example.com", "unknown_private_field": "private",
    }
    with Session(main.engine) as db:
        for index, (key, value) in enumerate(values.items(), start=10):
            q = Question(questionnaire_id="sample-initial-v1", key=key, prompt=key,
                         response_type="text", required=False, display_order=index, options=[])
            db.add(q)
            db.flush()
            db.add(StudentAnswer(student_id=sid, question_id=q.id, value=value))
        db.commit()
        context, _ = build_profile_context(db, sid, Settings(_env_file=None))
        for key in list(values)[:8]:
            assert context["answers"][key] == values[key]
        assert "accessibility_needs" in context["missing_fields"]
        assert context["omitted_field_count"] == 3
        assert "private" not in json.dumps(context).lower()


def test_openai_adapter_request_and_nonstorage(monkeypatch):
    client = MagicMock()
    client.responses.create.return_value = SimpleNamespace(status="completed", output_text="  Guidance  ")
    factory = MagicMock()
    factory.return_value.__enter__.return_value = client
    monkeypatch.setattr(llm_module, "OpenAI", factory)
    settings = Settings(_env_file=None, openai_api_key=SecretStr("test-key"), openai_model="test-model")
    service = OpenAILLMService(settings)
    messages = [{"role": "user", "content": "Hello"}]
    assert service.generate("Instructions", messages) == "Guidance"
    factory.assert_called_once_with(api_key="test-key", timeout=30, max_retries=0)
    client.responses.create.assert_called_once_with(
        model="test-model", instructions="Instructions", input=messages,
        max_output_tokens=1200, store=False)


@pytest.mark.parametrize("failure", ["connection", "timeout", 401, 429, 500])
def test_openai_errors_are_sanitized(monkeypatch, failure):
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    if failure == "connection":
        error = APIConnectionError(request=request)
    elif failure == "timeout":
        error = APITimeoutError(request=request)
    else:
        error = APIStatusError("PRIVATE PROVIDER DETAILS",
                               response=httpx.Response(failure, request=request), body=None)
    client = MagicMock()
    client.responses.create.side_effect = error
    factory = MagicMock()
    factory.return_value.__enter__.return_value = client
    monkeypatch.setattr(llm_module, "OpenAI", factory)
    with pytest.raises(LLMError) as result:
        OpenAILLMService(Settings(_env_file=None, openai_api_key="test-key")).generate("I", [])
    assert str(result.value) == "provider_unavailable"


@pytest.mark.parametrize("status,text", [("incomplete", "partial"), ("failed", ""), ("completed", " ")])
def test_incomplete_provider_response(monkeypatch, status, text):
    client = MagicMock()
    client.responses.create.return_value = SimpleNamespace(status=status, output_text=text)
    factory = MagicMock()
    factory.return_value.__enter__.return_value = client
    monkeypatch.setattr(llm_module, "OpenAI", factory)
    with pytest.raises(LLMError, match="provider_incomplete_response"):
        OpenAILLMService(Settings(_env_file=None, openai_api_key="test-key")).generate("I", [])


def test_missing_key_saves_student_message(client, fake_llm):
    main.app.dependency_overrides[get_llm] = lambda: OpenAILLMService(Settings(_env_file=None, openai_api_key=""))
    sid = student(client)
    response = client.post(f"/students/{sid}/chat", json={"message": "Hello"})
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "provider_not_configured"
    assert client.get(f"/students/{sid}/conversations/{detail['conversation_id']}").json()["messages"][0]["status"] == "failed"


def test_student_message_committed_before_generation(client, fake_llm):
    sid = student(client)

    def generate(instructions, messages):
        with Session(main.engine) as db:
            conversation = db.scalar(select(Conversation).where(Conversation.student_id == sid))
            saved = db.scalar(select(ConversationMessage).where(
                ConversationMessage.conversation_id == conversation.id))
            assert saved.content == "Save this before calling the provider"
            assert saved.status == "pending"
        return "A saved reply"

    fake_llm.generate = generate
    response = client.post(f"/students/{sid}/chat",
                           json={"message": "Save this before calling the provider"})
    assert response.status_code == 200


def test_out_of_order_replies_remain_in_turn_order(client, fake_llm):
    sid = student(client)
    with Session(main.engine) as db:
        conversation = Conversation(student_id=sid, questionnaire_id="sample-initial-v1")
        db.add(conversation)
        db.flush()
        cid = conversation.id
        first = ConversationMessage(conversation_id=cid, role="user", content="first", status="completed")
        second = ConversationMessage(conversation_id=cid, role="user", content="second", status="completed")
        db.add_all([first, second])
        db.flush()
        db.add(ConversationMessage(conversation_id=cid, role="assistant", content="second reply",
                                   reply_to_message_id=second.id))
        db.flush()
        db.add(ConversationMessage(conversation_id=cid, role="assistant", content="first reply",
                                   reply_to_message_id=first.id))
        db.add(ConversationMessage(conversation_id=cid, role="user", content="pending", status="pending"))
        db.commit()
        history = recent_history(db, cid, 999, 10, None)
        assert [m["content"] for m in history] == ["first", "first reply", "second", "second reply"]
    transcript = client.get(f"/students/{sid}/conversations/{cid}").json()["messages"]
    assert [m["content"] for m in transcript] == ["first", "first reply", "second", "second reply", "pending"]
