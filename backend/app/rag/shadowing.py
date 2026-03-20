"""
Shadowing de conflitos entre RAG e Dogmas Críticos.
"""

from collections import Counter
import math
import re
from typing import NamedTuple

INFRA_PATTERNS: dict[str, re.Pattern[str]] = {
    "port": re.compile(r"(?i)\b(?:port|porta)\s*[:=]?\s*(\d{2,5})\b"),
    "ipv4": re.compile(r"(?:\d{1,3}\.){3}\d{1,3}"),
    "path": re.compile(r"(?:/[a-zA-Z0-9_.-]+){2,}/?"),
    "env_var": re.compile(r"\b[A-Z][A-Z0-9_]*_[A-Z0-9_]+\b"),
}

DANGEROUS_CMD_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\brm\s+-rf\b"),
    re.compile(r"\beval\("),
    re.compile(r"\bos\.system\("),
    re.compile(r"\bsubprocess\.(?:call|run|Popen)\b"),
    re.compile(r"__import__\("),
]

JACCARD_THRESHOLD = 0.3
COSINE_THRESHOLD = 0.78


class ShadowResult(NamedTuple):
    should_shadow: bool
    reason: str
    matched_entities: list[str]
    jaccard_score: float
    cosine_sim: float


def has_dangerous_command(text: str) -> bool:
    lower = text.lower()
    return any(pattern.search(lower) for pattern in DANGEROUS_CMD_PATTERNS)


def _extract_entities(text: str) -> set[str]:
    entities: set[str] = set()
    for pattern in INFRA_PATTERNS.values():
        for match in pattern.finditer(text):
            entities.add(match.group(0).lower().strip())
    return entities


def _jaccard(set_a: set[str], set_b: set[str]) -> float:
    if not set_a or not set_b:
        return 0.0
    union = len(set_a | set_b)
    return len(set_a & set_b) / union if union else 0.0


def _cosine_token(text_a: str, text_b: str) -> float:
    token_pattern = re.compile(r"\w+")
    tokens_a = token_pattern.findall(text_a.lower())
    tokens_b = token_pattern.findall(text_b.lower())
    if not tokens_a or not tokens_b:
        return 0.0

    vec_a = Counter(tokens_a)
    vec_b = Counter(tokens_b)
    keys = set(vec_a) | set(vec_b)
    dot = sum(vec_a[k] * vec_b[k] for k in keys)
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


def check_shadow(rag_chunk_text: str, dogma_text: str) -> ShadowResult:
    rag_entities = _extract_entities(rag_chunk_text)
    dogma_entities = _extract_entities(dogma_text)
    shared = sorted(rag_entities & dogma_entities)

    if not shared:
        return ShadowResult(False, "sem entidades compartilhadas", [], 0.0, 0.0)

    jaccard = _jaccard(rag_entities, dogma_entities)
    if jaccard < JACCARD_THRESHOLD:
        return ShadowResult(False, f"jaccard {jaccard:.2f} < {JACCARD_THRESHOLD}", shared, jaccard, 0.0)

    cosine_text = _cosine_token(rag_chunk_text, dogma_text)
    cosine_entities = _cosine_token(" ".join(sorted(rag_entities)), " ".join(sorted(dogma_entities)))
    cosine = max(cosine_text, cosine_entities)
    if cosine < COSINE_THRESHOLD:
        return ShadowResult(
            False,
            f"cosine {cosine:.2f} < {COSINE_THRESHOLD}",
            shared,
            jaccard,
            cosine,
        )

    return ShadowResult(True, "conflito bivariável confirmado", shared, jaccard, cosine)


def apply_shadow_xml(chunk_text: str, source: str, dogma_rule: str, relevance_score: float) -> str:
    return (
        f'<retrieved_chunk source="{source}" relevance="{relevance_score:.2f}">\n'
        f'  <shadowed_text warning="CONFLITO COM DOGMA CRÍTICO: {dogma_rule}">\n'
        f"    {chunk_text}\n"
        f"  </shadowed_text>\n"
        f"</retrieved_chunk>"
    )


def process_chunk_against_dogmas(
    chunk_text: str,
    chunk_source: str,
    chunk_score: float,
    dogmas: list[dict],
) -> str:
    for dogma in dogmas:
        body = dogma.get("body", "")
        filepath = dogma.get("filepath", "dogma_desconhecido")
        result = check_shadow(chunk_text, body)
        if result.should_shadow:
            return apply_shadow_xml(
                chunk_text=chunk_text,
                source=chunk_source,
                dogma_rule=filepath,
                relevance_score=chunk_score,
            )

    return (
        f'<retrieved_chunk source="{chunk_source}" relevance="{chunk_score:.2f}">\n'
        f"  {chunk_text}\n"
        f"</retrieved_chunk>"
    )
