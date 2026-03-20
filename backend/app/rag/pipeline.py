"""
Orquestrador do pipeline RAG completo.
"""

import logging
from dataclasses import dataclass

from app.rag.jit_prompting import _cache, compile_constitution
from app.rag.scoring import ScoredChunk, score_and_rank
from app.rag.shadowing import process_chunk_against_dogmas

logger = logging.getLogger("grimoire.rag.pipeline")


@dataclass
class RAGContext:
    chunks_xml: str
    constitution: str
    top_k: int
    shadowed_count: int
    domains: list[str]


def build_rag_context(query: str, raw_chunks: list[dict], domains: list[str], top_k: int = 5) -> RAGContext:
    scored: list[ScoredChunk] = score_and_rank(query, raw_chunks, top_k=top_k)
    active_dogmas = _cache.get_for_domains(domains)

    shadowed_count = 0
    chunk_xmls: list[str] = []

    for scored_chunk in scored:
        xml = process_chunk_against_dogmas(
            chunk_text=scored_chunk.text,
            chunk_source=scored_chunk.source,
            chunk_score=scored_chunk.weighted_score,
            dogmas=active_dogmas,
        )
        if "<shadowed_text" in xml:
            shadowed_count += 1
        chunk_xmls.append(xml)

    chunks_xml = "<retrieved_chunks>\n" + "\n".join(chunk_xmls) + "\n</retrieved_chunks>"
    constitution = compile_constitution(domains)

    logger.info(
        "Pipeline RAG: %d chunks → %d top_k → %d shadowed | domínios: %s",
        len(raw_chunks),
        len(scored),
        shadowed_count,
        domains,
    )
    return RAGContext(
        chunks_xml=chunks_xml,
        constitution=constitution,
        top_k=top_k,
        shadowed_count=shadowed_count,
        domains=domains,
    )
