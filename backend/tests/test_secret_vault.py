import json
from datetime import datetime, timedelta, timezone

from app.security.pact_secret import get_current_pact_secret, verify_pact_signature
from app.security.secret_vault import (
    get_vault_secret,
    rotate_secret_if_due,
    set_vault_secret,
)


def test_pact_secret_rotation_keeps_previous_key(isolated_settings, monkeypatch):
    monkeypatch.delenv("GRIMOIRE_PACT_HMAC_SECRET", raising=False)

    current_key = "pact_hmac_secret_current"
    previous_key = "pact_hmac_secret_previous"
    set_vault_secret(current_key, "old-secret")

    state_path = isolated_settings.data_path / "security" / "rotation_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({current_key: (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()}),
        encoding="utf-8",
    )

    rotated = rotate_secret_if_due(
        current_key=current_key,
        previous_key=previous_key,
        period_seconds=10,
    )
    assert rotated
    assert get_vault_secret(previous_key) == "old-secret"
    assert get_vault_secret(current_key) != "old-secret"


def test_verify_pact_signature_uses_current_or_previous_key(isolated_settings, monkeypatch):
    monkeypatch.delenv("GRIMOIRE_PACT_HMAC_SECRET", raising=False)
    from app.models.pacts import InquisitorReport, StatelessPactModel, ToolCallIntent

    set_vault_secret("pact_hmac_secret_current", "secret-current")
    set_vault_secret("pact_hmac_secret_previous", "secret-previous")

    pact = StatelessPactModel.create(
        session_id="session_prev_key_001",
        entity_manifest_hash="h",
        operator_proposal_raw="q",
        tool_intent=ToolCallIntent(tool_name="llm_generate", literal_arguments={"query": "q"}),
        critic_report=[InquisitorReport(severity="INFO", technical_reasoning="ok")],
        secret_key=b"secret-previous",
    )
    assert verify_pact_signature(pact)

    _ = get_current_pact_secret()
