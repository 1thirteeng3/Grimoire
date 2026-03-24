import asyncio
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.integrations.obsidian_cli import ObsidianCliError
from app.llm.deepseek_client import LLMProviderError
from app.main import app
from app.rag.pipeline import RAGContext


def _receive_until(ws, expected_type: str, max_reads: int = 20):
    for _ in range(max_reads):
        payload = json.loads(ws.receive_text())
        if payload.get("type") == expected_type:
            return payload
    raise AssertionError(f"Evento {expected_type} não recebido em {max_reads} leituras")


def _receive_until_stream_contains(ws, fragment: str, max_reads: int = 30):
    for _ in range(max_reads):
        payload = json.loads(ws.receive_text())
        if payload.get("type") == "STREAM_TOKEN" and fragment in payload.get("payload", {}).get("delta", ""):
            return payload
    raise AssertionError(f"STREAM_TOKEN contendo '{fragment}' não recebido em {max_reads} leituras")


def test_ws_intent_happy_path_e2e(isolated_settings, monkeypatch):
    async def fake_stream(*args, **kwargs):
        del args, kwargs
        for token in ["fluxo", " e2e", " ok"]:
            yield token

    monkeypatch.setattr("app.api.ws_gateway.stream_operator_response", fake_stream)
    monkeypatch.setattr(
        "app.api.ws_gateway.retrieve_relevant_chunks",
        lambda **kwargs: [
            {
                "text": "Deploy seguro usando rollback.",
                "source": "obsidian:runbooks/deploy.md",
                "memory_type": "obsidian_vault",
            }
        ],
    )

    with TestClient(app) as client:
        with client.websocket_connect("/ws/session_e2e_happy_001") as ws:
            ws.send_text(
                json.dumps(
                    {
                        "type": "INTENT_SUBMIT",
                        "query": "Como fazer deploy seguro?",
                        "domains": ["generic"],
                    }
                )
            )
            rag_event = _receive_until(ws, "STATE_RAG_RETRIEVAL")
            assert rag_event["payload"]["documents_scanned"] == 1
            execution = _receive_until(ws, "EXECUTION_SUCCESS")
            assert "fluxo e2e ok" in execution["payload"]["stdout"]


def test_prompt_bloat_path_e2e(isolated_settings, monkeypatch):
    monkeypatch.setattr(
        "app.api.ws_gateway.build_rag_context",
        lambda **kwargs: RAGContext(
            chunks_xml="<retrieved_chunks/>",
            constitution="",
            top_k=5,
            shadowed_count=0,
            domains=["generic"],
            prompt_bloat={"current_tokens": 9000, "limit": 4096, "domain": "generic"},
        ),
    )
    monkeypatch.setattr("app.api.ws_gateway.retrieve_relevant_chunks", lambda **kwargs: [])

    with TestClient(app) as client:
        with client.websocket_connect("/ws/session_e2e_bloat_001") as ws:
            ws.send_text(json.dumps({"type": "INTENT_SUBMIT", "query": "q", "domains": ["generic"]}))
            event = _receive_until(ws, "PROMPT_BLOATING")
            assert event["payload"]["limit"] == 4096


def test_invalid_signature_path_e2e(isolated_settings):
    from app.persistence.sqlite_layer import save_pact

    pact_id = str(uuid4())
    future_ttl = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    pact = {
        "pact_id": pact_id,
        "session_id": "session_e2e_invalid_sig",
        "entity_manifest_hash": "abc123",
        "fsm_status": "PENDING_HUMAN_CONFLICT",
        "operator_proposal_raw": "print('safe')",
        "tool_intent": {"tool_name": "execute_python", "literal_arguments": {"code": "print('safe')"}},
        "critic_report": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ttl_timestamp": future_ttl,
        "cryptographic_signature": "sha256=invalid",
    }

    with TestClient(app) as client:
        asyncio.run(save_pact(json.dumps(pact), pact_id))
        response = client.post(
            f"/api/v1/pacts/{pact_id}/resolve",
            json={"action": "APPROVE_AS_IS", "modified_arguments": {}},
        )
        assert response.status_code == 403
        assert response.json()["error_code"] == "PACT_SIGNATURE_INVALID"


def test_obsidian_cli_unavailable_path_e2e(isolated_settings, monkeypatch):
    async def fake_stream(*args, **kwargs):
        del args, kwargs
        for token in ["obsidian", " indisponível", " fallback ok"]:
            yield token

    monkeypatch.setattr("app.api.ws_gateway.stream_operator_response", fake_stream)
    monkeypatch.setattr("app.rag.retrieval.search_documents", lambda **kwargs: [])
    monkeypatch.setattr(
        "app.rag.retrieval.read_note",
        lambda _: (_ for _ in ()).throw(ObsidianCliError("obsidian missing")),
    )

    with TestClient(app) as client:
        with client.websocket_connect("/ws/session_e2e_obsidian_001") as ws:
            ws.send_text(
                json.dumps(
                    {
                        "type": "INTENT_SUBMIT",
                        "query": "responda mesmo sem vault",
                        "domains": ["generic"],
                        "obsidian_note_paths": ["runbooks/missing.md"],
                    }
                )
            )
            execution = _receive_until(ws, "EXECUTION_SUCCESS")
            assert "fallback ok" in execution["payload"]["stdout"]


def test_llm_provider_unavailable_path_e2e(isolated_settings, monkeypatch):
    async def provider_down(*args, **kwargs):
        del args, kwargs
        raise LLMProviderError("provider indisponível")
        yield "never"  # pragma: no cover

    monkeypatch.setattr("app.api.ws_gateway.stream_operator_response", provider_down)
    monkeypatch.setattr("app.api.ws_gateway.retrieve_relevant_chunks", lambda **kwargs: [])
    monkeypatch.setattr(
        "app.api.ws_gateway.build_rag_context",
        lambda **kwargs: RAGContext(
            chunks_xml="<retrieved_chunks/>",
            constitution="<leis_ativas/>",
            top_k=1,
            shadowed_count=0,
            domains=["generic"],
            prompt_bloat=None,
        ),
    )

    with TestClient(app) as client:
        with client.websocket_connect("/ws/session_e2e_provider_001") as ws:
            ws.send_text(json.dumps({"type": "INTENT_SUBMIT", "query": "responda", "domains": ["generic"]}))
            event = _receive_until_stream_contains(ws, "Falha no provedor LLM")
            assert "provider indisponível" in event["payload"]["delta"]
