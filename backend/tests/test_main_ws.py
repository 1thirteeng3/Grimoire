import json

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
