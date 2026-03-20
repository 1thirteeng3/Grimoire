import json
import asyncio

from fastapi.testclient import TestClient

from app.main import app
from app.rag.pipeline import RAGContext


def _receive_until(ws, expected_type: str, max_reads: int = 10):
    for _ in range(max_reads):
        payload = json.loads(ws.receive_text())
        if payload.get("type") == expected_type:
            return payload
    raise AssertionError(f"Evento {expected_type} não recebido em {max_reads} leituras")


def test_health_and_startup_paths(isolated_settings):
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert (isolated_settings.data_path / "grimoire.db").exists()
        assert "copilot-introspector" in app.state.entities


def test_websocket_ping_pong_and_intent_flow(isolated_settings):
    with TestClient(app) as client:
        with client.websocket_connect("/ws/session_test_001") as ws:
            ws.send_text(json.dumps({"type": "PING"}))
            pong = _receive_until(ws, "PONG")
            assert pong["type"] == "PONG"

            ws.send_text(json.dumps({"type": "INTENT_SUBMIT", "query": "oi", "chunks": [], "domains": ["generic"]}))
            ws.send_text(json.dumps({"type": "PACT_RESOLVE"}))
            ws.send_text(json.dumps({"type": "PING"}))
            pong2 = _receive_until(ws, "PONG")
            assert pong2["type"] == "PONG"

            ws.send_text(json.dumps({"type": "UNKNOWN_TYPE"}))


def test_websocket_emits_prompt_bloating_event(isolated_settings, monkeypatch):
    monkeypatch.setattr(
        "app.api.ws_gateway.build_rag_context",
        lambda **kwargs: RAGContext(
            chunks_xml="<retrieved_chunks/>",
            constitution="",
            top_k=5,
            shadowed_count=0,
            domains=["generic"],
            prompt_bloat={"current_tokens": 5000, "limit": 4096, "domain": "generic"},
        ),
    )
    with TestClient(app) as client:
        with client.websocket_connect("/ws/session_test_002") as ws:
            ws.send_text(json.dumps({"type": "INTENT_SUBMIT", "query": "q", "chunks": [], "domains": ["generic"]}))
            event = _receive_until(ws, "PROMPT_BLOATING")
            assert event["payload"]["limit"] == 4096


def test_websocket_streams_llm_response(isolated_settings, monkeypatch):
    async def fake_stream(*args, **kwargs):
        del args, kwargs
        for token in ["Olá", " ", "mundo"]:
            yield token

    monkeypatch.setattr("app.api.ws_gateway.stream_operator_response", fake_stream)
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
        with client.websocket_connect("/ws/session_test_003") as ws:
            ws.send_text(json.dumps({"type": "INTENT_SUBMIT", "query": "responda", "chunks": [], "domains": []}))
            execution = _receive_until(ws, "EXECUTION_SUCCESS")
            assert execution["payload"]["exit_code"] == 0
            assert "Olá mundo" in execution["payload"]["stdout"]


def test_websocket_pact_request_and_resolve_flow(isolated_settings, monkeypatch):
    async def fake_stream(*args, **kwargs):
        del args, kwargs
        for token in ["Aprovado", " com", " pacto"]:
            yield token

    monkeypatch.setattr("app.api.ws_gateway.stream_operator_response", fake_stream)
    monkeypatch.setattr(
        "app.api.ws_gateway.build_rag_context",
        lambda **kwargs: RAGContext(
            chunks_xml="<retrieved_chunks><retrieved_chunk source='x' relevance='1.0'><shadowed_text warning='x'>y</shadowed_text></retrieved_chunk></retrieved_chunks>",
            constitution="<leis_ativas/>",
            top_k=1,
            shadowed_count=1,
            domains=["generic"],
            prompt_bloat=None,
        ),
    )

    with TestClient(app) as client:
        with client.websocket_connect("/ws/session_pact_loop_001") as ws:
            ws.send_text(
                json.dumps(
                    {
                        "type": "INTENT_SUBMIT",
                        "query": "Faça um deploy",
                        "chunks": [],
                        "domains": ["generic"],
                    }
                )
            )
            pact_event = _receive_until(ws, "PACT_REQUEST")
            pact_id = pact_event["payload"]["pact_id"]
            assert pact_id
            ws.send_text(
                json.dumps(
                    {
                        "type": "PACT_RESOLVE",
                        "pact_id": pact_id,
                        "action": "APPROVE_AS_IS",
                    }
                )
            )
            execution = _receive_until(ws, "EXECUTION_SUCCESS", max_reads=30)
            assert "Aprovado com pacto" in execution["payload"]["stdout"]

    from app.persistence.sqlite_layer import fetch_pact_audit_events

    audit_events = asyncio.run(fetch_pact_audit_events(pact_id))
    event_types = [event["event_type"] for event in audit_events]
    assert "PACT_CREATED" in event_types
    assert "PACT_REQUEST_EMITTED" in event_types
    assert "PACT_APPROVED_BY_HUMAN" in event_types
    assert "EXECUTION_STARTED" in event_types
    assert "EXECUTION_SUCCEEDED" in event_types


def test_websocket_pact_abort_flow(isolated_settings, monkeypatch):
    monkeypatch.setattr(
        "app.api.ws_gateway.build_rag_context",
        lambda **kwargs: RAGContext(
            chunks_xml="<retrieved_chunks/>",
            constitution="<leis_ativas/>",
            top_k=1,
            shadowed_count=1,
            domains=["generic"],
            prompt_bloat=None,
        ),
    )

    with TestClient(app) as client:
        with client.websocket_connect("/ws/session_pact_abort_001") as ws:
            ws.send_text(
                json.dumps(
                    {
                        "type": "INTENT_SUBMIT",
                        "query": "rm -rf /tmp",
                        "chunks": [],
                        "domains": ["generic"],
                    }
                )
            )
            pact_event = _receive_until(ws, "PACT_REQUEST")
            pact_id = pact_event["payload"]["pact_id"]
            ws.send_text(
                json.dumps(
                    {
                        "type": "PACT_RESOLVE",
                        "pact_id": pact_id,
                        "action": "ABORT",
                    }
                )
            )
            message = _receive_until(ws, "STREAM_TOKEN")
            assert "abortado" in message["payload"]["delta"].lower()
