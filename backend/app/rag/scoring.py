"""
Cross-Encoder scoring com logits brutos ONNX.
"""

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

from app.config import settings

logger = logging.getLogger("grimoire.rag.scoring")

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


def _fallback_score(query: str, text: str, memory_type: str) -> float:
    query_terms = set(query.lower().split())
    text_terms = set(text.lower().split())
    overlap = len(query_terms & text_terms)
    lexical = overlap / max(1, len(query_terms))
    weight = MEMORY_WEIGHTS.get(memory_type, 1.0)
    return lexical * weight


def score_and_rank(query: str, chunks: list[dict], top_k: int = 5) -> list[ScoredChunk]:
    if not chunks:
        return []

    try:
        model, tokenizer = _load_model()
        pairs = [(query, c["text"]) for c in chunks]
        inputs = tokenizer(pairs, padding=True, truncation=True, max_length=512, return_tensors="pt")

        outputs = model(**inputs)
        raw_logits = np.asarray(outputs.logits.detach().numpy())
        if raw_logits.ndim == 0:
            logits = [float(raw_logits.item())]
        elif raw_logits.ndim == 1:
            if raw_logits.shape[0] == len(chunks):
                logits = raw_logits.astype(float).tolist()
            elif len(chunks) == 1:
                # Explicit policy for single-sample multi-class outputs.
                logits = [float(raw_logits[0])]
            else:
                raise ValueError(
                    f"Formato de logits 1D incompatível: shape={raw_logits.shape}, chunks={len(chunks)}"
                )
        elif raw_logits.ndim == 2:
            if raw_logits.shape[0] != len(chunks):
                raise ValueError(
                    f"Formato de logits 2D incompatível: shape={raw_logits.shape}, chunks={len(chunks)}"
                )
            # Explicit policy: use first class logit deterministically.
            logits = raw_logits[:, 0].astype(float).tolist()
        else:
            raise ValueError(f"Formato de logits não suportado: shape={raw_logits.shape}")
    except Exception as exc:
        logger.warning("ONNX reranker indisponível, aplicando fallback lexical: %s", exc)
        scored = []
        for chunk in chunks:
            memory_type = chunk.get("memory_type", "vector_rag")
            weighted = _fallback_score(query, chunk["text"], memory_type)
            scored.append(
                ScoredChunk(
                    text=chunk["text"],
                    source=chunk.get("source", "unknown"),
                    memory_type=memory_type,
                    raw_logit=weighted,
                    weighted_score=weighted,
                )
            )
        scored.sort(key=lambda x: x.weighted_score, reverse=True)
        return scored[:top_k]

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
