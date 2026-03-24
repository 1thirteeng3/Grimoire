from fastapi import APIRouter, Depends, Response

from app.observability.slo import slo_snapshot
from app.observability import telemetry_prometheus, telemetry_snapshot
from app.security import maybe_require_metrics_auth, require_scopes_dep, rest_rate_limit_dep

router = APIRouter(dependencies=[Depends(rest_rate_limit_dep())])
prometheus_router = APIRouter(include_in_schema=False)


@router.get("/observability/metrics")
async def get_operational_metrics(
    _principal=Depends(require_scopes_dep("observability:read")),
):
    return telemetry_snapshot()


@router.get("/observability/slo")
async def get_slo_definitions(
    _principal=Depends(require_scopes_dep("observability:read")),
):
    return slo_snapshot()


@prometheus_router.get("/metrics")
async def get_prometheus_metrics(
    _rate_limit=Depends(rest_rate_limit_dep()),
    _principal=Depends(maybe_require_metrics_auth),
):
    return Response(
        content=telemetry_prometheus(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
