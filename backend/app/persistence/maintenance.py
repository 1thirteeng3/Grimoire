import logging

from app.config import settings
from app.observability import enforce_metrics_retention
from app.persistence import db

logger = logging.getLogger("grimoire.persistence.maintenance")


async def run_retention_cycle() -> dict[str, int | bool]:
    expired_pacts = await db.purge_expired_pacts()
    audit_deleted = await db.purge_old_audit_events(settings.retention_audit_days)
    routing_deleted = await db.purge_old_routing_events(settings.retention_routing_days)
    summaries_deleted = await db.purge_old_session_summaries(settings.retention_session_summary_days)
    metrics_reset = enforce_metrics_retention(settings.metrics_retention_seconds)

    result: dict[str, int | bool] = {
        "expired_pacts": expired_pacts,
        "audit_deleted": audit_deleted,
        "routing_deleted": routing_deleted,
        "summaries_deleted": summaries_deleted,
        "metrics_reset": metrics_reset,
    }
    if expired_pacts or audit_deleted or routing_deleted or summaries_deleted or metrics_reset:
        logger.info("Retention cycle concluído: %s", result)
    return result
