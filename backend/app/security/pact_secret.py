import os

from app.config import settings
from app.models.pacts import StatelessPactModel
from app.security.secret_vault import get_or_create_vault_secret, get_vault_secret, rotate_secret_if_due


def _env_override_secret() -> str | None:
    value = os.getenv("GRIMOIRE_PACT_HMAC_SECRET")
    if value and value.strip():
        return value.strip()
    return None


def get_current_pact_secret() -> bytes:
    env_secret = _env_override_secret()
    if env_secret:
        return env_secret.encode()

    rotate_secret_if_due(
        current_key=settings.pact_secret_current_vault_key,
        previous_key=settings.pact_secret_previous_vault_key,
        period_seconds=settings.pact_secret_rotation_seconds,
    )
    current = get_or_create_vault_secret(settings.pact_secret_current_vault_key)
    return current.encode()


def get_pact_verification_secrets() -> list[bytes]:
    env_secret = _env_override_secret()
    if env_secret:
        return [env_secret.encode()]

    current = get_or_create_vault_secret(settings.pact_secret_current_vault_key)
    previous = get_vault_secret(settings.pact_secret_previous_vault_key)
    values = [current.encode()]
    if previous:
        values.append(previous.encode())
    return values


def verify_pact_signature(pact: StatelessPactModel) -> bool:
    return any(pact.verify_signature(secret) for secret in get_pact_verification_secrets())
