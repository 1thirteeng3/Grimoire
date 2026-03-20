from fastapi import APIRouter, Response

from app.observability import telemetry_prometheus, telemetry_snapshot

router = APIRouter()
prometheus_router = APIRouter(include_in_schema=False)


@router.get("/observability/metrics")
async def get_operational_metrics():
    return telemetry_snapshot()


@prometheus_router.get("/metrics")
async def get_prometheus_metrics():
    return Response(
        content=telemetry_prometheus(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
