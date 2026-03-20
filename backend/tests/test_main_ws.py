import json
import asyncio

from fastapi.testclient import TestClient

from app.llm.deepseek_client import LLMConfigurationError, LLMProviderError
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


def test_observability_metrics_endpoint_tracks_ws_rag_llm(isolated_settings, monkeypatch):
    async def fake_stream(*args, **kwargs):
        del args, kwargs
        for token in ["resposta", " final"]:
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
        with client.websocket_connect("/ws/session_obs_001") as ws:
            ws.send_text(json.dumps({"type": "INTENT_SUBMIT", "query": "responda", "chunks": [], "domains": []}))
            _ = _receive_until(ws, "EXECUTION_SUCCESS")

        metrics = client.get("/api/v1/observability/metrics")
        assert metrics.status_code == 200
        payload = metrics.json()
        assert payload["stages"]["WS"]["count"] >= 1
        assert payload["stages"]["RAG"]["count"] >= 1
        assert payload["stages"]["LLM"]["count"] >= 1
        assert payload["tokens"]["input"] > 0
        assert payload["tokens"]["output"] > 0


def test_prometheus_metrics_export_format(isolated_settings, monkeypatch):
    async def fake_stream(*args, **kwargs):
        del args, kwargs
        for token in ["resposta", " final"]:
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
        with client.websocket_connect("/ws/session_obs_prom_001") as ws:
            ws.send_text(json.dumps({"type": "INTENT_SUBMIT", "query": "responda", "chunks": [], "domains": []}))
            _ = _receive_until(ws, "EXECUTION_SUCCESS")

        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert "text/plain" in metrics.headers["content-type"]
        body = metrics.text
        assert "# HELP grimoire_stage_latency_ms_total" in body
        assert 'grimoire_stage_latency_ms_total{stage="LLM"}' in body
        assert 'grimoire_tokens_total{direction="input"}' in body


def test_prometheus_metrics_export_includes_error_series(isolated_settings, monkeypatch):
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
    with TestClient(app) as client:
        with client.websocket_connect("/ws/session_obs_prom_err_001") as ws:
            ws.send_text(json.dumps({"type": "INTENT_SUBMIT", "query": "q", "chunks": [], "domains": ["generic"]}))
            _ = _receive_until(ws, "PROMPT_BLOATING")

        body = client.get("/metrics").text
        assert 'grimoire_errors_total{stage="RAG",error_type="PROMPT_BLOAT"}' in body
        assert 'grimoire_error_rate_over_ws{stage="RAG",error_type="PROMPT_BLOAT"}' in body


def test_observability_error_rate_for_prompt_bloat(isolated_settings, monkeypatch):
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
    with TestClient(app) as client:
        with client.websocket_connect("/ws/session_obs_bloat_001") as ws:
            ws.send_text(json.dumps({"type": "INTENT_SUBMIT", "query": "q", "chunks": [], "domains": ["generic"]}))
            _ = _receive_until(ws, "PROMPT_BLOATING")

        payload = client.get("/api/v1/observability/metrics").json()
        assert payload["errors"]["RAG:PROMPT_BLOAT"] >= 1
        assert payload["error_rates_over_ws"]["RAG:PROMPT_BLOAT"] > 0


def test_observability_error_rate_for_auth_and_timeout(isolated_settings, monkeypatch):
    async def auth_fail(*args, **kwargs):
        del args, kwargs
        raise LLMConfigurationError("Falha de autenticação no DeepSeek (401/403).")
        yield "never"  # pragma: no cover

    monkeypatch.setattr("app.api.ws_gateway.stream_operator_response", auth_fail)
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
        with client.websocket_connect("/ws/session_obs_auth_001") as ws:
            ws.send_text(json.dumps({"type": "INTENT_SUBMIT", "query": "responda", "chunks": [], "domains": []}))
            _ = _receive_until(ws, "STREAM_TOKEN")
        payload = client.get("/api/v1/observability/metrics").json()
        assert payload["errors"]["LLM:LLM_AUTH"] >= 1

    async def timeout_fail(*args, **kwargs):
        del args, kwargs
        raise LLMProviderError("Timeout no provedor DeepSeek em 60s.")
        yield "never"  # pragma: no cover

    monkeypatch.setattr("app.api.ws_gateway.stream_operator_response", timeout_fail)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/session_obs_timeout_001") as ws:
            ws.send_text(json.dumps({"type": "INTENT_SUBMIT", "query": "responda", "chunks": [], "domains": []}))
            _ = _receive_until(ws, "STREAM_TOKEN")
        payload = client.get("/api/v1/observability/metrics").json()
        assert payload["errors"]["LLM:LLM_PROVIDER_TIMEOUT"] >= 1
