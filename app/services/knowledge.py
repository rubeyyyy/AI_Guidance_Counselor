"""Curated JSON documents and a persistent, career-only Chroma index."""
import hashlib
import json
from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.core.config import Settings


class KnowledgeDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    document_id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9_-]+$")
    title: str = Field(min_length=1)
    category: str = Field(min_length=1)
    source_organization: str = Field(min_length=1)
    source_url: HttpUrl | None
    verification_date: date
    is_sample: bool
    content: str = Field(min_length=1)

    @model_validator(mode="after")
    def source_requirements(self):
        if not self.is_sample and self.source_url is None:
            raise ValueError("Non-sample documents require an actual source URL")
        if self.verification_date > date.today():
            raise ValueError("Verification date cannot be in the future")
        return self


def load_documents(directory: Path) -> list[KnowledgeDocument]:
    if not directory.is_dir():
        raise ValueError(f"Knowledge directory does not exist: {directory}")
    documents = []
    seen = set()
    for path in sorted(directory.rglob("*.json")):
        try:
            document = KnowledgeDocument.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError as error:
            raise ValueError(f"Invalid knowledge document: {path.name}: {error}") from error
        if document.document_id in seen:
            raise ValueError(f"Duplicate document_id: {document.document_id}")
        seen.add(document.document_id)
        documents.append(document)
    return documents


def collection_name(settings: Settings) -> str:
    # A model change must never silently query incompatible vectors.
    digest = hashlib.sha256(settings.openai_embedding_model.encode()).hexdigest()[:12]
    return f"pathbridge-careers-{digest}"


def chroma_client(settings: Settings):
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    return chromadb.PersistentClient(
        path=str(settings.chroma_persist_directory.resolve()),
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def knowledge_status(settings: Settings) -> dict:
    result = {"enabled": settings.rag_enabled, "initialized": False,
              "documents": 0, "chunks": 0, "state": "not_initialized"}
    if not (settings.chroma_persist_directory / "chroma.sqlite3").is_file():
        return result
    client = chroma_client(settings)
    if collection_name(settings) not in [c.name for c in client.list_collections()]:
        return result
    collection = client.get_collection(collection_name(settings))
    records = collection.get(include=["metadatas"])
    result.update(initialized=True, chunks=len(records["ids"]), state="ready",
                  documents=len({m["document_id"] for m in records["metadatas"]}))
    return result


def make_embeddings(settings: Settings):
    from langchain_openai import OpenAIEmbeddings

    if not settings.openai_api_key.get_secret_value().strip():
        raise ValueError("OPENAI_API_KEY is required for embeddings")
    return OpenAIEmbeddings(model=settings.openai_embedding_model,
                            api_key=settings.openai_api_key,
                            request_timeout=settings.openai_timeout_seconds, max_retries=0)


def vector_store(settings: Settings, embeddings):
    from langchain_chroma import Chroma

    return Chroma(client=chroma_client(settings), collection_name=collection_name(settings),
                  embedding_function=embeddings, collection_metadata={"hnsw:space": "cosine"})


def ingest(directory: Path, settings: Settings, embeddings=None) -> dict:
    """Synchronize this directory as the complete index; reruns skip unchanged chunks.

    Validate everything and embed new chunks before deleting superseded chunks.
    Run one ingestion process at a time, with chat stopped during updates.
    """
    from langchain_core.documents import Document
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    documents = load_documents(directory)
    if not documents:
        raise ValueError("No JSON documents found; refusing to clear the index")
    splitter = RecursiveCharacterTextSplitter(chunk_size=settings.rag_chunk_size,
                                             chunk_overlap=settings.rag_chunk_overlap)
    chunks, ids = [], []
    for document in documents:
        metadata = document.model_dump(mode="json", exclude={"content"})
        metadata["source_url"] = metadata["source_url"] or ""
        for index, content in enumerate(splitter.split_text(document.content)):
            identity = json.dumps([metadata, index, content], sort_keys=True)
            chunk_id = hashlib.sha256(identity.encode()).hexdigest()
            chunks.append(Document(page_content=content, metadata={**metadata, "chunk_index": index}))
            ids.append(chunk_id)
    store = vector_store(settings, embeddings if embeddings is not None else make_embeddings(settings))
    existing = set(store.get(include=[])["ids"])
    new = [(chunk, cid) for chunk, cid in zip(chunks, ids) if cid not in existing]
    # Batch explicitly to stay within Chroma's write limit.
    for start in range(0, len(new), 100):
        batch = new[start:start + 100]
        store.add_documents([chunk for chunk, _ in batch], ids=[cid for _, cid in batch])
    stale = sorted(existing - set(ids))
    for start in range(0, len(stale), 100):
        store.delete(ids=stale[start:start + 100])
    return {"documents": len(documents), "chunks": len(chunks),
            "chunks_added": len(new), "chunks_removed": len(stale)}
