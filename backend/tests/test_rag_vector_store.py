from app.config import settings
from app.rag.vector_store import RetrievedChunk, search_documents, upsert_documents


def test_upsert_documents_returns_false_when_collection_unavailable(monkeypatch):
    monkeypatch.setattr("app.rag.vector_store._ensure_collection", lambda: False)
    assert not upsert_documents([{"text": "x", "source": "s"}])


def test_upsert_documents_success(monkeypatch):
    monkeypatch.setattr("app.rag.vector_store._ensure_collection", lambda: True)
    monkeypatch.setattr("app.rag.vector_store._encode", lambda texts: [[0.1, 0.2] for _ in texts])
    calls = {}

    class FakeClient:
        def upsert(self, collection_name, points):
            calls["collection_name"] = collection_name
            calls["points"] = points

    monkeypatch.setattr("app.rag.vector_store._get_client", lambda: FakeClient())
    ok = upsert_documents(
        [{"text": "abc", "source": "obsidian:A.md", "memory_type": "obsidian_vault", "domain": "devops"}]
    )
    assert ok
    assert calls["collection_name"] == settings.qdrant_collection
    assert len(calls["points"]) == 1


def test_search_documents_maps_payload(monkeypatch):
    monkeypatch.setattr("app.rag.vector_store._ensure_collection", lambda: True)
    monkeypatch.setattr("app.rag.vector_store._encode", lambda texts: [[0.1, 0.2]])

    class FakeRow:
        def __init__(self, score, payload):
            self.score = score
            self.payload = payload

    class FakeClient:
        def search(self, **kwargs):
            return [
                FakeRow(0.9, {"text": "um", "source": "s1", "memory_type": "vector_rag"}),
                FakeRow(0.01, {"text": "dois", "source": "s2", "memory_type": "vector_rag"}),
            ]

    monkeypatch.setattr("app.rag.vector_store._get_client", lambda: FakeClient())
    monkeypatch.setattr(settings, "retrieval_min_score", 0.1)
    chunks = search_documents("consulta", ["generic"], top_k=5)
    assert chunks == [RetrievedChunk(text="um", source="s1", memory_type="vector_rag", score=0.9)]


def test_search_documents_returns_empty_on_error(monkeypatch):
    monkeypatch.setattr("app.rag.vector_store._ensure_collection", lambda: True)
    monkeypatch.setattr("app.rag.vector_store._encode", lambda texts: [[0.1, 0.2]])

    class FakeClient:
        def search(self, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr("app.rag.vector_store._get_client", lambda: FakeClient())
    assert search_documents("consulta", ["generic"]) == []
