import json
import logging
import threading
from collections import defaultdict
from time import perf_counter
from typing import Any

logger = logging.getLogger("grimoire.observability")

_lock = threading.RLock()
_stage_stats: dict[str, dict[str, float | int]] = defaultdict(
    lambda: {"count": 0, "errors": 0, "total_ms": 0.0, "max_ms": 0.0}
)
_token_stats: dict[str, int] = defaultdict(int)
_error_stats: dict[str, int] = defaultdict(int)
_requests_total: int = 0

_encoder = None
_tiktoken_available = True


def _structured_log(event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    logger.info(json.dumps(payload, ensure_ascii=False, default=str))


def start_timer() -> float:
    return perf_counter()


def elapsed_ms(start: float) -> float:
    return (perf_counter() - start) * 1000.0


def record_stage_latency(stage: str, duration_ms: float, status: str = "ok", **context: Any) -> None:
    global _requests_total
    with _lock:
        stats = _stage_stats[stage]
        stats["count"] = int(stats["count"]) + 1
        stats["total_ms"] = float(stats["total_ms"]) + float(duration_ms)
        stats["max_ms"] = max(float(stats["max_ms"]), float(duration_ms))
        if status != "ok":
            stats["errors"] = int(stats["errors"]) + 1
        if stage == "WS":
            _requests_total += 1
    _structured_log(
        "stage_latency",
        stage=stage,
        duration_ms=round(duration_ms, 2),
        status=status,
        **context,
    )


def record_tokens(direction: str, count: int, **context: Any) -> None:
    safe_count = max(0, int(count))
    with _lock:
        _token_stats[direction] += safe_count
    _structured_log("token_usage", direction=direction, count=safe_count, **context)


def record_error(error_type: str, stage: str, **context: Any) -> None:
    key = f"{stage}:{error_type}"
    with _lock:
        _error_stats[key] += 1
        total = max(1, _requests_total)
        current_rate = _error_stats[key] / total
    _structured_log(
        "error_counter",
        stage=stage,
        error_type=error_type,
        count=_error_stats[key],
        rate_over_ws=round(current_rate, 6),
        **context,
    )


def estimate_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    global _encoder, _tiktoken_available
    if not text:
        return 0
    if _tiktoken_available:
        try:
            if _encoder is None:
                import tiktoken

                _encoder = tiktoken.get_encoding(encoding_name)
            return int(len(_encoder.encode(text)))
        except Exception:
            _tiktoken_available = False
    return len(text.split())


def telemetry_snapshot() -> dict[str, Any]:
    with _lock:
        stage_snapshot: dict[str, Any] = {}
        for stage, stats in _stage_stats.items():
            count = int(stats["count"])
            total_ms = float(stats["total_ms"])
            stage_snapshot[stage] = {
                "count": count,
                "errors": int(stats["errors"]),
                "avg_ms": round(total_ms / max(1, count), 2),
                "max_ms": round(float(stats["max_ms"]), 2),
            }

        error_rates: dict[str, float] = {}
        denominator = max(1, _requests_total)
        for key, count in _error_stats.items():
            error_rates[key] = round(count / denominator, 6)

        return {
            "requests_total": _requests_total,
            "stages": stage_snapshot,
            "tokens": dict(_token_stats),
            "errors": dict(_error_stats),
            "error_rates_over_ws": error_rates,
        }


def reset_telemetry() -> None:
    global _requests_total
    with _lock:
        _stage_stats.clear()
        _token_stats.clear()
        _error_stats.clear()
        _requests_total = 0
