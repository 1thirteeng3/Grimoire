from unittest.mock import patch

import pytest

from app.rag.pipeline import RAGContext, build_rag_context


@pytest.fixture
def mock_scoring(monkeypatch):
    from app.rag.scoring import ScoredChunk

    mock_results = [
        ScoredChunk(
            text="Use porta 80. Porta 80 para HTTP.",
            source="nginx.md",
            memory_type="vector_rag",
            raw_logit=1.5,
            weighted_score=1.5,
        ),
        ScoredChunk(
            text="redis cache pattern",
            source="redis.md",
            memory_type="vector_rag",
            raw_logit=0.8,
            weighted_score=0.8,
        ),
    ]
    monkeypatch.setattr("app.rag.pipeline.score_and_rank", lambda *a, **k: mock_results)
    return mock_results


@pytest.fixture
def mock_dogmas(monkeypatch):
    fake_dogmas = [
        {"body": "PROIBIDO: porta 80 em produção. Porta 80 deve ser bloqueada.", "filepath": "regra_rede.md"}
    ]
    monkeypatch.setattr("app.rag.pipeline._cache.get_for_domains", lambda d: fake_dogmas)
    monkeypatch.setattr("app.rag.pipeline.compile_constitution", lambda d: "<leis_ativas>ok</leis_ativas>")
    return fake_dogmas


def test_pipeline_executa_shadowing(mock_scoring, mock_dogmas):
    del mock_scoring, mock_dogmas
    ctx = build_rag_context(
        query="configurar nginx",
        raw_chunks=[{"text": "t", "source": "s", "memory_type": "vector_rag"}],
        domains=["devops"],
    )
    assert isinstance(ctx, RAGContext)
    assert ctx.shadowed_count >= 1
    assert "<shadowed_text" in ctx.chunks_xml


def test_pipeline_retorna_constituicao(mock_scoring, mock_dogmas):
    del mock_scoring, mock_dogmas
    ctx = build_rag_context("q", [], ["software"])
    assert "leis_ativas" in ctx.constitution


def test_pipeline_chunks_vazios_sem_erro(mock_dogmas):
    del mock_dogmas
    with patch("app.rag.pipeline.score_and_rank", return_value=[]):
        ctx = build_rag_context("q", [], ["software"])
        assert ctx.top_k == 5
        assert ctx.shadowed_count == 0


def test_pipeline_sem_dogmas_nao_shadow(monkeypatch):
    from app.rag.scoring import ScoredChunk

    monkeypatch.setattr(
        "app.rag.pipeline.score_and_rank",
        lambda *a, **k: [
            ScoredChunk(
                text="Use Redis para cache",
                source="redis.md",
                memory_type="vector_rag",
                raw_logit=0.9,
                weighted_score=0.9,
            )
        ],
    )
    monkeypatch.setattr("app.rag.pipeline._cache.get_for_domains", lambda d: [])
    monkeypatch.setattr("app.rag.pipeline.compile_constitution", lambda d: "")
    ctx = build_rag_context("cache", [{"text": "x", "source": "y", "memory_type": "vector_rag"}], ["software"])
    assert ctx.shadowed_count == 0
    assert "<shadowed_text" not in ctx.chunks_xml
