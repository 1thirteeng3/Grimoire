from fastapi import APIRouter

from app.observability import telemetry_snapshot

router = APIRouter()


@router.get("/observability/metrics")
async def get_operational_metrics():
    return telemetry_snapshot()
