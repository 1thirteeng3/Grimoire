"""
Cross-Encoder scoring com logits brutos ONNX.
"""

from dataclasses import dataclass
from typing import Any

from app.config import settings

MEMORY_WEIGHTS: dict[str, float] = {
    "critical_dogma": 3.0,
    "obsidian_vault": 2.0,
    "vector_rag": 1.0,
}


@dataclass
class ScoredChunk:
    text: str
    source: str
    memory_type: str
    raw_logit: float
    weighted_score: float


_model: Any = None
_tokenizer: Any = None


def _load_model() -> tuple[Any, Any]:
    global _model, _tokenizer
    if _model is None or _tokenizer is None:
        from optimum.onnxruntime import ORTModelForSequenceClassification
        from transformers import AutoTokenizer

        model_path = str(settings.onnx_model_path)
        _model = ORTModelForSequenceClassification.from_pretrained(model_path)
        _tokenizer = AutoTokenizer.from_pretrained(model_path)
    return _model, _tokenizer


def score_and_rank(query: str, chunks: list[dict], top_k: int = 5) -> list[ScoredChunk]:
    if not chunks:
        return []

    model, tokenizer = _load_model()
    pairs = [(query, c["text"]) for c in chunks]
    inputs = tokenizer(pairs, padding=True, truncation=True, max_length=512, return_tensors="pt")

    outputs = model(**inputs)
    logits = outputs.logits.detach().numpy().squeeze().tolist()
    if isinstance(logits, float):
        logits = [logits]

    scored: list[ScoredChunk] = []
    for chunk, logit in zip(chunks, logits):
        memory_type = chunk.get("memory_type", "vector_rag")
        weight = MEMORY_WEIGHTS.get(memory_type, 1.0)
        weighted = float(logit) * weight
        scored.append(
            ScoredChunk(
                text=chunk["text"],
                source=chunk.get("source", "unknown"),
                memory_type=memory_type,
                raw_logit=float(logit),
                weighted_score=weighted,
            )
        )

    scored.sort(key=lambda x: x.weighted_score, reverse=True)
    return scored[:top_k]
