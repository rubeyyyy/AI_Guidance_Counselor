import json
import math
from pathlib import Path

import pytest
from langchain_core.embeddings import Embeddings

from app import main
from app.core.config import Settings, get_settings
from app.services.knowledge import ingest, knowledge_status, load_documents
from app.services.retrieval import RetrievalService, get_retrieval, topic_query
from tests.test_chat import fake_llm, student  # noqa: F401
from tests.test_students import client  # noqa: F401


class MockEmbeddings(Embeddings):
    """Deterministic topic vectors; no network, model downloads, or API keys."""
    def __init__(self):
        self.queries = []
        self.documents = []

    def vector(self, text):
        values = [float(word in text.lower()) for word in ("programming", "nursing", "admissions")]
        values.append(0.01)
        length = math.sqrt(sum(v * v for v in values))
        return [v / length for v in values]

    def embed_documents(self, texts):
        self.documents.extend(texts)
        return [self.vector(t) for t in texts]

    def embed_query(self, text):
        self.queries.append(text)
        return self.vector(text)


@pytest.fixture
def rag(tmp_path):
    settings = Settings(_env_file=None, rag_enabled=True,
                        chroma_persist_directory=tmp_path / "vectors", rag_top_k=1)
    directory = tmp_path / "knowledge"
    directory.mkdir()
    document = {
        "document_id": "test-programming", "title": "SAMPLE programming guidance",
        "category": "programming", "source_organization": "Fictional test fixture",
        "source_url": "https://example.org/test-fixture", "verification_date": "2026-01-01",
        "is_sample": True, "content": "SAMPLE: Explore programming by planning a small project on paper.",
    }
    path = directory / "programming.json"
    path.write_text(json.dumps(document))
    return settings, directory, path, document, MockEmbeddings()


def test_load_validation_and_duplicate_ids(rag):
    _, directory, path, document, _ = rag
    assert load_documents(directory)[0].document_id == "test-programming"
    for change in [{"title": " "}, {"source_url": "not a URL"},
                   {"is_sample": False, "source_url": None},
                   {"verification_date": "2999-01-01"}]:
        path.write_text(json.dumps({**document, **change}))
        with pytest.raises(ValueError, match="Invalid knowledge document"):
            load_documents(directory)
    missing = dict(document)
    missing.pop("source_organization")
    path.write_text(json.dumps(missing))
    with pytest.raises(ValueError):
        load_documents(directory)
    path.write_text(json.dumps(document))
    (directory / "duplicate.json").write_text(json.dumps(document))
    with pytest.raises(ValueError, match="Duplicate document_id"):
        load_documents(directory)


def test_ingest_idempotence_update_and_deletion(rag):
    settings, directory, path, document, embeddings = rag
    assert not knowledge_status(settings)["initialized"]
    first = ingest(directory, settings, embeddings)
    assert first == {"documents": 1, "chunks": 1, "chunks_added": 1, "chunks_removed": 0}
    assert ingest(directory, settings, embeddings)["chunks_added"] == 0
    assert len(embeddings.documents) == 1
    document["content"] = "Updated programming guidance. " * 100
    path.write_text(json.dumps(document))
    updated = ingest(directory, settings, embeddings)
    assert updated["chunks_removed"] == 1 and updated["chunks"] > 1
    assert knowledge_status(settings)["chunks"] == updated["chunks"]
    # A replacement document with a new ID removes all old chunks.
    document.update(document_id="replacement", content="Programming replacement")
    path.write_text(json.dumps(document))
    result = ingest(directory, settings, embeddings)
    assert result["chunks_removed"] == updated["chunks"]
    assert knowledge_status(settings)["documents"] == 1
    path.write_text("{}")
    with pytest.raises(ValueError):
        ingest(directory, settings, embeddings)
    assert knowledge_status(settings)["chunks"] == 1  # Validation before mutation.


def test_retrieval_sources_privacy_and_insufficient_evidence(rag):
    settings, directory, _, _, embeddings = rag
    ingest(directory, settings, embeddings)
    service = RetrievalService(settings, embeddings)
    context = {"is_sample": False, "answers": {
        "interests": "Programming with Private Name private@example.org",
        "accessibility_needs": "private condition", "constraints": "private finances",
        "name": "Private Name", "email": "private@example.org"}}
    result = service.retrieve("Private Name private@example.org wants programming advice", context)
    assert result.state == "retrieved"
    excerpt = result.excerpts[0]
    assert excerpt["document_id"] == "test-programming"
    assert excerpt["source_url"] == "https://example.org/test-fixture"
    assert excerpt["title"] == "SAMPLE programming guidance"
    assert excerpt["is_sample"] is True
    assert embeddings.queries == ["programming"]
    assert service.retrieve("Nursing", {}).state == "insufficient"
    assert service.retrieve("Tell me about astronomy", {}).state == "no_supported_topics"
    assert topic_query("Hello", {"is_sample": True, "answers": {"interests": "nursing"}}) == ""
    assert "NOT verified" in result.instructions()


def test_failed_embedding_keeps_previous_index_and_model_isolation(rag):
    settings, directory, path, document, embeddings = rag
    ingest(directory, settings, embeddings)
    document["content"] = "Changed programming guidance"
    path.write_text(json.dumps(document))

    class FailingEmbeddings(MockEmbeddings):
        def embed_documents(self, texts):
            raise RuntimeError("Embedding unavailable")

    with pytest.raises(RuntimeError, match="Embedding unavailable"):
        ingest(directory, settings, FailingEmbeddings())
    assert knowledge_status(settings)["chunks"] == 1
    result = RetrievalService(settings, embeddings).retrieve("Programming", {})
    assert result.excerpts[0]["content"].startswith("SAMPLE: Explore programming")
    settings.openai_embedding_model = "different-model"
    assert not knowledge_status(settings)["initialized"]


def test_chat_insufficient_evidence(client, fake_llm, rag):
    settings, directory, _, _, embeddings = rag
    ingest(directory, settings, embeddings)
    main.app.dependency_overrides[get_settings] = lambda: settings
    main.app.dependency_overrides[get_retrieval] = lambda: RetrievalService(settings, embeddings)
    sid = student(client)
    response = client.post(f"/students/{sid}/chat", json={"message": "What are nursing requirements?"})
    assert response.status_code == 200
    instructions, _ = fake_llm.calls[-1]
    assert '"state": "insufficient"' in instructions
    assert '"excerpts": []' in instructions
    assert "Never extrapolate eligibility, costs" in instructions


def test_status_missing_and_unreadable(client, rag, monkeypatch):
    settings, _, _, _, _ = rag
    main.app.dependency_overrides[get_settings] = lambda: settings
    response = client.get("/knowledge-base/status")
    assert response.json()["state"] == "not_initialized"
    assert not settings.chroma_persist_directory.exists()

    def unavailable(settings):
        raise RuntimeError("Private local path or provider details")

    monkeypatch.setattr("app.api.knowledge_base.knowledge_status", unavailable)
    response = client.get("/knowledge-base/status")
    assert response.status_code == 200
    assert response.json()["state"] == "unavailable"
    assert "Private" not in response.text


def test_empty_disabled_and_unavailable_without_paid_calls(rag, monkeypatch):
    settings, _, _, _, embeddings = rag
    service = RetrievalService(settings, embeddings)
    assert service.retrieve("Programming", {}).state == "empty"
    assert embeddings.queries == []
    settings.rag_enabled = False
    assert service.retrieve("Programming", {}).state == "disabled"
    settings.rag_enabled = True
    monkeypatch.setattr("app.services.retrieval.knowledge_status", lambda s: {"chunks": 1})
    monkeypatch.setattr("app.services.retrieval.vector_store", lambda *a: (_ for _ in ()).throw(RuntimeError("secret")))
    result = service.retrieve("Programming", {})
    assert result.state == "unavailable" and "secret" not in result.instructions()


def test_chat_rag_sources_history_and_response_compatibility(client, fake_llm, rag):
    settings, directory, _, _, embeddings = rag
    ingest(directory, settings, embeddings)
    main.app.dependency_overrides[get_settings] = lambda: settings
    main.app.dependency_overrides[get_retrieval] = lambda: RetrievalService(settings, embeddings)
    sid = student(client, "Private Name")

    def grounded_reply(instructions, messages):
        fake_llm.calls.append((instructions, messages))
        assert '"document_id": "test-programming"' in instructions
        assert "https://example.org/test-fixture" in instructions
        assert "Private Name" not in instructions
        return "General SAMPLE guidance: plan a small programming project on paper [test-programming]. Source: SAMPLE programming guidance (https://example.org/test-fixture). The knowledge base lacks verified program evidence; discuss your plan with a counselor."

    fake_llm.generate = grounded_reply
    response = client.post(f"/students/{sid}/chat", json={"message": "How can I explore programming?"})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"conversation_id", "student_message", "assistant_message"}
    assert "[test-programming]" in body["assistant_message"]["content"]
    detail = client.get(f"/students/{sid}/conversations/{body['conversation_id']}").json()
    assert detail["messages"][-1]["content"] == body["assistant_message"]["content"]
    status = client.get("/knowledge-base/status").json()
    assert status == {"enabled": True, "initialized": True, "documents": 1, "chunks": 1, "state": "ready"}


@pytest.mark.parametrize("enabled,question,state", [
    (False, "Programming", "disabled"), (True, "Programming", "empty"),
    (True, "Unrecognized topic", "no_supported_topics"),
])
def test_chat_no_evidence_behavior(client, fake_llm, rag, enabled, question, state):
    settings, _, _, _, embeddings = rag
    settings.rag_enabled = enabled
    main.app.dependency_overrides[get_settings] = lambda: settings
    main.app.dependency_overrides[get_retrieval] = lambda: RetrievalService(settings, embeddings)
    sid = student(client)
    response = client.post(f"/students/{sid}/chat", json={"message": question})
    assert response.status_code == 200
    instructions, _ = fake_llm.calls[-1]
    assert f'"state": "{state}"' in instructions
    assert "explicitly say" in instructions and "lacks verified evidence" in instructions
    assert embeddings.queries == []


def test_sample_documents_validate():
    directory = Path(__file__).resolve().parents[1] / "knowledge_base"
    documents = load_documents(directory)
    assert len(documents) == 3
    assert all(d.is_sample and d.source_url is None for d in documents)
