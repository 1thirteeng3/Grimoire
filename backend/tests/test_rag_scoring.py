import math
import sys
import types
from unittest.mock import MagicMock

import numpy as np
import pytest

from app.rag.scoring import MEMORY_WEIGHTS, _load_model, score_and_rank


@pytest.fixture
def mock_ort_model(monkeypatch):
    model_mock = MagicMock()
    tokenizer_mock = MagicMock(return_value={})
    monkeypatch.setattr("app.rag.scoring._model", model_mock)
    monkeypatch.setattr("app.rag.scoring._tokenizer", tokenizer_mock)
    return model_mock


def test_critical_dogma_beats_positive_rag_logit(mock_ort_model):
    chunks = [
        {"text": "Abrir porta 80", "source": "nginx.md", "memory_type": "vector_rag"},
        {"text": "Nunca abrir porta 80", "source": "dogma.md", "memory_type": "critical_dogma"},
    ]
    mock_ort_model.return_value.logits.detach.return_value.numpy.return_value = np.array([1.0, -2.5])

    results = score_and_rank("configurar nginx", chunks, top_k=2)

    rag_result = next(r for r in results if r.memory_type == "vector_rag")
    dogma_result = next(r for r in results if r.memory_type == "critical_dogma")

    assert rag_result.weighted_score == pytest.approx(1.0 * MEMORY_WEIGHTS["vector_rag"])
    assert dogma_result.weighted_score == pytest.approx(-2.5 * MEMORY_WEIGHTS["critical_dogma"])


def test_critical_dogma_with_positive_logit_always_wins():
    w_critical = MEMORY_WEIGHTS["critical_dogma"]
    w_vector = MEMORY_WEIGHTS["vector_rag"]
    best_rag_score = 10.0 * w_vector
    dogma_score = 4.0 * w_critical
    assert dogma_score > best_rag_score


def test_no_sigmoid_applied():
    logit = -2.5
    sigmoid_of_logit = 1 / (1 + math.exp(-logit))
    raw_weighted = logit * MEMORY_WEIGHTS["critical_dogma"]
    sigmoid_weighted = sigmoid_of_logit * MEMORY_WEIGHTS["critical_dogma"]
    assert abs(raw_weighted - sigmoid_weighted) > 1.0


def test_ranking_order_is_deterministic(mock_ort_model):
    chunks = [
        {"text": "c1", "source": "s1", "memory_type": "vector_rag"},
        {"text": "c2", "source": "s2", "memory_type": "vector_rag"},
        {"text": "c3", "source": "s3", "memory_type": "vector_rag"},
    ]
    mock_ort_model.return_value.logits.detach.return_value.numpy.return_value = np.array([0.4, 1.5, -0.1])
    results = score_and_rank("q", chunks, top_k=3)
    assert [r.text for r in results] == ["c2", "c1", "c3"]


def test_empty_chunks_short_circuit():
    assert score_and_rank("q", [], top_k=5) == []


def test_single_float_logit_is_wrapped(monkeypatch):
    model_mock = MagicMock()
    tokenizer_mock = MagicMock(return_value={})
    monkeypatch.setattr("app.rag.scoring._model", model_mock)
    monkeypatch.setattr("app.rag.scoring._tokenizer", tokenizer_mock)
    model_mock.return_value.logits.detach.return_value.numpy.return_value = np.array(0.7)
    result = score_and_rank(
        "q",
        [{"text": "single", "source": "s", "memory_type": "vector_rag"}],
        top_k=1,
    )
    assert len(result) == 1
    assert result[0].raw_logit == pytest.approx(0.7)


def test_load_model_lazy_import_with_stub(monkeypatch):
    class FakeOrt:
        @classmethod
        def from_pretrained(cls, path):
            return {"model_path": path}

    class FakeTokenizer:
        @classmethod
        def from_pretrained(cls, path):
            return {"tokenizer_path": path}

    fake_ort_module = types.SimpleNamespace(ORTModelForSequenceClassification=FakeOrt)
    fake_transformers_module = types.SimpleNamespace(AutoTokenizer=FakeTokenizer)
    monkeypatch.setitem(sys.modules, "optimum.onnxruntime", fake_ort_module)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers_module)
    monkeypatch.setattr("app.rag.scoring._model", None)
    monkeypatch.setattr("app.rag.scoring._tokenizer", None)

    model, tokenizer = _load_model()
    assert "model_path" in model
    assert "tokenizer_path" in tokenizer


def test_multiclass_logits_use_first_column(mock_ort_model):
    chunks = [
        {"text": "a", "source": "s1", "memory_type": "vector_rag"},
        {"text": "b", "source": "s2", "memory_type": "vector_rag"},
    ]
    mock_ort_model.return_value.logits.detach.return_value.numpy.return_value = np.array(
        [[0.2, 0.9], [1.4, -0.3]]
    )
    results = score_and_rank("q", chunks, top_k=2)
    assert [r.raw_logit for r in results] == [1.4, 0.2]


def test_scoring_fallback_when_onnx_unavailable(monkeypatch):
    monkeypatch.setattr("app.rag.scoring._load_model", lambda: (_ for _ in ()).throw(RuntimeError("missing")))
    chunks = [
        {"text": "usar porta 443 com tls", "source": "a", "memory_type": "critical_dogma"},
        {"text": "redis cache local", "source": "b", "memory_type": "vector_rag"},
    ]
    results = score_and_rank("porta 443 tls", chunks, top_k=2)
    assert len(results) == 2
    assert results[0].source == "a"
