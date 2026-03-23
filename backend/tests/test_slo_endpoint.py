from fastapi.testclient import TestClient

from app.main import app
from app.observability.telemetry import record_stage_latency, reset_telemetry


def test_observability_slo_endpoint_exposes_objectives(isolated_settings):
    del isolated_settings
    reset_telemetry()
    record_stage_latency("WS", 12.0, status="ok")
    record_stage_latency("RAG", 640.0, status="ok")
    record_stage_latency("LLM", 2200.0, status="ok")

    with TestClient(app) as client:
        response = client.get("/api/v1/observability/slo")
    assert response.status_code == 200
    payload = response.json()

    assert payload["window"] == "rolling_30d"
    assert payload["requests_total"] >= 1
    objectives = {item["sli"] for item in payload["objectives"]}
    assert "ws_availability" in objectives
    assert "ws_error_ratio" in objectives
    assert "rag_avg_latency_ms" in objectives
    assert "llm_avg_latency_ms" in objectives

    assert payload["current"]["ws_availability"] >= 0.0
    assert payload["current"]["ws_error_ratio"] >= 0.0
