import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.security.auth import AuthPrincipal


def _registry_with_tokens() -> dict[str, AuthPrincipal]:
    return {
        "admin-token": AuthPrincipal(
            subject="admin",
            scopes=frozenset(
                {
                    "pacts:read",
                    "pacts:write",
                    "observability:read",
                    "metrics:read",
                    "ws:connect",
                    "ws:write",
                }
            ),
        ),
        "observer-token": AuthPrincipal(
            subject="observer",
            scopes=frozenset({"pacts:read", "observability:read", "metrics:read"}),
        ),
        "ws-readonly-token": AuthPrincipal(
            subject="ws-readonly",
            scopes=frozenset({"ws:connect"}),
        ),
    }


def test_rest_authentication_and_authorization(isolated_settings, monkeypatch):
    monkeypatch.setattr("app.security.auth.settings.auth_required", True)
    monkeypatch.setattr("app.security.auth._token_registry", _registry_with_tokens)

    with TestClient(app) as client:
        no_auth = client.get("/api/v1/pacts/nonexistent/audit")
        assert no_auth.status_code == 401

        read_auth = client.get(
            "/api/v1/pacts/nonexistent/audit",
            headers={"Authorization": "Bearer observer-token"},
        )
        assert read_auth.status_code == 404

        forbidden_write = client.post(
            "/api/v1/pacts/nonexistent/resolve",
            headers={"Authorization": "Bearer observer-token"},
            json={"action": "APPROVE_AS_IS"},
        )
        assert forbidden_write.status_code == 403

        admin_write = client.post(
            "/api/v1/pacts/nonexistent/resolve",
            headers={"Authorization": "Bearer admin-token"},
            json={"action": "APPROVE_AS_IS"},
        )
        assert admin_write.status_code == 404


def test_metrics_auth_when_enabled(isolated_settings, monkeypatch):
    monkeypatch.setattr("app.security.auth.settings.auth_required", True)
    monkeypatch.setattr("app.security.auth.settings.metrics_require_auth", True)
    monkeypatch.setattr("app.security.auth._token_registry", _registry_with_tokens)

    with TestClient(app) as client:
        no_auth = client.get("/metrics")
        assert no_auth.status_code == 401

        with_auth = client.get("/metrics", headers={"Authorization": "Bearer observer-token"})
        assert with_auth.status_code == 200
        assert "grimoire_" in with_auth.text


def test_ws_auth_required_blocks_connection(isolated_settings, monkeypatch):
    monkeypatch.setattr("app.security.auth.settings.auth_required", True)
    monkeypatch.setattr("app.security.auth._token_registry", _registry_with_tokens)

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/ws_auth_required_001"):
                pass


def test_ws_scope_forbidden_for_write_message(isolated_settings, monkeypatch):
    monkeypatch.setattr("app.security.auth.settings.auth_required", True)
    monkeypatch.setattr("app.security.auth._token_registry", _registry_with_tokens)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/ws_scope_001?token=ws-readonly-token") as ws:
            ws.send_text(json.dumps({"type": "INTENT_SUBMIT", "query": "hello", "domains": ["generic"]}))
            payload = json.loads(ws.receive_text())
            assert payload["type"] == "STREAM_TOKEN"
            assert "Escopo insuficiente" in payload["payload"]["delta"]


def test_rest_rate_limit_returns_429(isolated_settings, monkeypatch):
    monkeypatch.setattr("app.security.auth.settings.auth_required", False)
    monkeypatch.setattr("app.security.rate_limit.settings.rest_rate_limit_per_minute", 1)

    with TestClient(app) as client:
        first = client.get("/api/v1/observability/metrics")
        assert first.status_code == 200
        second = client.get("/api/v1/observability/metrics")
        assert second.status_code == 429


def test_ws_rate_limit_disconnects_abusive_client(isolated_settings, monkeypatch):
    monkeypatch.setattr("app.security.auth.settings.auth_required", False)
    monkeypatch.setattr("app.security.rate_limit.settings.ws_rate_limit_per_minute_per_ip", 2)
    monkeypatch.setattr("app.security.rate_limit.settings.ws_rate_limit_per_minute_per_session", 2)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/ws_rate_limit_001") as ws:
            ws.send_text(json.dumps({"type": "PING"}))
            pong = json.loads(ws.receive_text())
            assert pong["type"] == "PONG"

            ws.send_text(json.dumps({"type": "PING"}))
            _ = json.loads(ws.receive_text())

            ws.send_text(json.dumps({"type": "PING"}))
            limit_msg = json.loads(ws.receive_text())
            assert limit_msg["type"] == "STREAM_TOKEN"
            assert "Rate limit atingido" in limit_msg["payload"]["delta"]
            with pytest.raises(WebSocketDisconnect):
                ws.receive_text()
