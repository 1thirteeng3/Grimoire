import json

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def test_health_and_startup_paths(tmp_path):
    settings.data_path = tmp_path / "data"
    settings.vault_path = tmp_path / "vault"
    settings.entities_path = tmp_path / "entities"

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert (settings.data_path / "grimoire.db").exists()
        assert "copilot-introspector" in app.state.entities


def test_websocket_ping_pong_and_intent_flow(tmp_path):
    settings.data_path = tmp_path / "data"
    settings.vault_path = tmp_path / "vault"
    settings.entities_path = tmp_path / "entities"

    with TestClient(app) as client:
        with client.websocket_connect("/ws/session_test_001") as ws:
            ws.send_text(json.dumps({"type": "PING"}))
            pong = json.loads(ws.receive_text())
            assert pong["type"] == "PONG"

            ws.send_text(json.dumps({"type": "INTENT_SUBMIT"}))
            ws.send_text(json.dumps({"type": "PACT_RESOLVE"}))
            ws.send_text(json.dumps({"type": "PING"}))
            pong2 = json.loads(ws.receive_text())
            assert pong2["type"] == "PONG"

            ws.send_text(json.dumps({"type": "UNKNOWN_TYPE"}))
