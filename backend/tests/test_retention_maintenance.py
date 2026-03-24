import pytest

from app.persistence.maintenance import run_retention_cycle


@pytest.mark.asyncio
async def test_run_retention_cycle(monkeypatch):
    monkeypatch.setattr("app.persistence.maintenance.settings.retention_audit_days", 30)
    monkeypatch.setattr("app.persistence.maintenance.settings.retention_routing_days", 10)
    monkeypatch.setattr("app.persistence.maintenance.settings.retention_session_summary_days", 15)
    monkeypatch.setattr("app.persistence.maintenance.settings.metrics_retention_seconds", 1)

    async def _return_one(*args, **kwargs):
        del args, kwargs
        return 1

    monkeypatch.setattr("app.persistence.maintenance.db.purge_expired_pacts", _return_one)
    monkeypatch.setattr("app.persistence.maintenance.db.purge_old_audit_events", _return_one)
    monkeypatch.setattr("app.persistence.maintenance.db.purge_old_routing_events", _return_one)
    monkeypatch.setattr("app.persistence.maintenance.db.purge_old_session_summaries", _return_one)
    monkeypatch.setattr("app.persistence.maintenance.enforce_metrics_retention", lambda _: True)

    result = await run_retention_cycle()
    assert result["expired_pacts"] == 1
    assert result["audit_deleted"] == 1
    assert result["routing_deleted"] == 1
    assert result["summaries_deleted"] == 1
    assert result["metrics_reset"] is True
