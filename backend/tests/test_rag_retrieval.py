from app.rag.retrieval import retrieve_relevant_chunks


def test_retrieval_returns_vector_results(monkeypatch):
    monkeypatch.setattr("app.rag.retrieval.upsert_documents", lambda docs: True)
    monkeypatch.setattr(
        "app.rag.retrieval.search_documents",
        lambda **kwargs: [
            type("R", (), {"text": "from vector", "source": "qdrant", "memory_type": "vector_rag"})()
        ],
    )
    result = retrieve_relevant_chunks(
        query="deploy",
        domains=["devops"],
        manual_chunks=[{"text": "manual", "source": "m", "memory_type": "vector_rag"}],
    )
    assert len(result) == 1
    assert result[0]["source"] == "qdrant"


def test_retrieval_fallbacks_to_lexical_when_vector_empty(monkeypatch):
    monkeypatch.setattr("app.rag.retrieval.upsert_documents", lambda docs: True)
    monkeypatch.setattr("app.rag.retrieval.search_documents", lambda **kwargs: [])
    result = retrieve_relevant_chunks(
        query="abrir porta 443",
        domains=["devops"],
        manual_chunks=[
            {"text": "usar porta 443 com tls", "source": "a", "memory_type": "vector_rag"},
            {"text": "redis cache local", "source": "b", "memory_type": "vector_rag"},
        ],
    )
    assert result
    assert result[0]["source"] == "a"


def test_retrieval_uses_existing_index_without_new_candidates(monkeypatch):
    monkeypatch.setattr(
        "app.rag.retrieval.search_documents",
        lambda **kwargs: [
            type("R", (), {"text": "already indexed", "source": "obsidian:x", "memory_type": "obsidian_vault"})()
        ],
    )
    result = retrieve_relevant_chunks(query="arquitetura", domains=["software_engineering"], manual_chunks=None)
    assert result
    assert result[0]["text"] == "already indexed"


def test_retrieval_returns_empty_when_no_candidates_or_index(monkeypatch):
    monkeypatch.setattr("app.rag.retrieval.search_documents", lambda **kwargs: [])
    result = retrieve_relevant_chunks(query="x", domains=["generic"], manual_chunks=None)
    assert result == []
