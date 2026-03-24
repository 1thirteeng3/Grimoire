import logging
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from app.config import settings

logger = logging.getLogger("grimoire.rag.vector")


@dataclass
class RetrievedChunk:
    text: str
    source: str
    memory_type: str
    score: float


_client: Any = None
_embedder: Any = None
_collection_ready: bool = False


def _build_doc_id(source: str, text: str) -> str:
    digest = sha256(f"{source}\n{text}".encode("utf-8")).hexdigest()
    return digest


def _get_client():
    global _client
    if _client is not None:
        return _client
    from qdrant_client import QdrantClient

    if settings.qdrant_mode == "server":
        _client = QdrantClient(url=settings.qdrant_url)
    else:
        _client = QdrantClient(path=str(settings.qdrant_local_path))
    return _client


def _get_embedder():
    global _embedder
    if _embedder is not None:
        return _embedder
    from sentence_transformers import SentenceTransformer

    _embedder = SentenceTransformer(settings.embedding_model_id)
    return _embedder


def _ensure_collection() -> bool:
    global _collection_ready
    if _collection_ready:
        return True
    try:
        client = _get_client()
        embedder = _get_embedder()
        from qdrant_client.http import models as qmodels

        dimension = int(embedder.get_sentence_embedding_dimension())
        collections = client.get_collections().collections
        if not any(c.name == settings.qdrant_collection for c in collections):
            client.create_collection(
                collection_name=settings.qdrant_collection,
                vectors_config=qmodels.VectorParams(size=dimension, distance=qmodels.Distance.COSINE),
            )
        _collection_ready = True
        return True
    except Exception as exc:
        logger.warning("Qdrant/embedding indisponível, fallback lexical ativado: %s", exc)
        return False


def _encode(texts: list[str]) -> list[list[float]]:
    embedder = _get_embedder()
    vectors = embedder.encode(texts, normalize_embeddings=True)
    return [list(map(float, vec)) for vec in vectors]


def upsert_documents(documents: list[dict[str, str]]) -> bool:
    if not documents:
        return True
    if not _ensure_collection():
        return False
    try:
        client = _get_client()
        from qdrant_client.http import models as qmodels

        vectors = _encode([doc["text"] for doc in documents])
        points: list[qmodels.PointStruct] = []
        for doc, vector in zip(documents, vectors):
            source = doc.get("source", "unknown")
            text = doc.get("text", "")
            memory_type = doc.get("memory_type", "vector_rag")
            domain = doc.get("domain", "generic")
            points.append(
                qmodels.PointStruct(
                    id=_build_doc_id(source, text),
                    vector=vector,
                    payload={
                        "text": text,
                        "source": source,
                        "memory_type": memory_type,
                        "domain": domain,
                    },
                )
            )
        client.upsert(collection_name=settings.qdrant_collection, points=points)
        return True
    except Exception as exc:
        logger.warning("Falha ao indexar no Qdrant, fallback lexical ativado: %s", exc)
        return False


def search_documents(query: str, domains: list[str], top_k: int | None = None) -> list[RetrievedChunk]:
    if not query.strip():
        return []
    if not _ensure_collection():
        return []
    try:
        client = _get_client()
        from qdrant_client.http import models as qmodels

        query_vector = _encode([query])[0]
        filter_obj = None
        if domains:
            filter_obj = qmodels.Filter(
                should=[
                    qmodels.FieldCondition(
                        key="domain",
                        match=qmodels.MatchValue(value=str(domain)),
                    )
                    for domain in domains
                ]
            )
        result = client.search(
            collection_name=settings.qdrant_collection,
            query_vector=query_vector,
            query_filter=filter_obj,
            limit=int(top_k or settings.retrieval_top_k),
            with_payload=True,
        )
        chunks: list[RetrievedChunk] = []
        for row in result:
            payload = row.payload or {}
            score = float(row.score or 0.0)
            if score < settings.retrieval_min_score:
                continue
            chunks.append(
                RetrievedChunk(
                    text=str(payload.get("text", "")),
                    source=str(payload.get("source", "unknown")),
                    memory_type=str(payload.get("memory_type", "vector_rag")),
                    score=score,
                )
            )
        return chunks
    except Exception as exc:
        logger.warning("Falha na busca vetorial, fallback lexical ativado: %s", exc)
        return []
