from __future__ import annotations

from typing import Any

from app.observability.telemetry import telemetry_snapshot

SLO_WINDOW = "rolling_30d"

SLO_OBJECTIVES: list[dict[str, Any]] = [
    {
        "sli": "ws_availability",
        "target": 0.995,
        "unit": "ratio",
        "description": "Disponibilidade operacional do gateway WS (mensagens sem erro de etapa).",
        "promql": (
            "1 - (rate(grimoire_stage_errors_total{stage=\"WS\"}[5m]) / "
            "clamp_min(rate(grimoire_stage_operations_total{stage=\"WS\"}[5m]), 0.001))"
        ),
    },
    {
        "sli": "ws_error_ratio",
        "target": 0.01,
        "unit": "ratio",
        "description": "Taxa máxima de erro agregada no fluxo WS.",
        "promql": (
            "rate(grimoire_stage_errors_total{stage=\"WS\"}[5m]) / "
            "clamp_min(rate(grimoire_stage_operations_total{stage=\"WS\"}[5m]), 0.001)"
        ),
    },
    {
        "sli": "rag_avg_latency_ms",
        "target": 1200.0,
        "unit": "milliseconds",
        "description": "Latência média do estágio RAG.",
        "promql": (
            "rate(grimoire_stage_latency_ms_total{stage=\"RAG\"}[5m]) / "
            "clamp_min(rate(grimoire_stage_operations_total{stage=\"RAG\"}[5m]), 0.001)"
        ),
    },
    {
        "sli": "llm_avg_latency_ms",
        "target": 3500.0,
        "unit": "milliseconds",
        "description": "Latência média do estágio LLM.",
        "promql": (
            "rate(grimoire_stage_latency_ms_total{stage=\"LLM\"}[5m]) / "
            "clamp_min(rate(grimoire_stage_operations_total{stage=\"LLM\"}[5m]), 0.001)"
        ),
    },
]


def slo_snapshot() -> dict[str, Any]:
    snapshot = telemetry_snapshot()
    stages = snapshot.get("stages", {})
    ws = stages.get("WS", {})
    rag = stages.get("RAG", {})
    llm = stages.get("LLM", {})

    ws_count = max(1, int(ws.get("count", 0) or 0))
    ws_errors = int(ws.get("errors", 0) or 0)
    availability = 1.0 - (ws_errors / ws_count)
    ws_error_ratio = ws_errors / ws_count

    current = {
        "ws_availability": round(max(0.0, min(1.0, availability)), 6),
        "ws_error_ratio": round(max(0.0, min(1.0, ws_error_ratio)), 6),
        "rag_avg_latency_ms": float(rag.get("avg_ms", 0.0) or 0.0),
        "llm_avg_latency_ms": float(llm.get("avg_ms", 0.0) or 0.0),
    }

    return {
        "window": SLO_WINDOW,
        "objectives": SLO_OBJECTIVES,
        "current": current,
        "requests_total": int(snapshot.get("requests_total", 0) or 0),
    }
