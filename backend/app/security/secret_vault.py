import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings
from app.core.secrets import get_secret, set_secret


def _rotation_state_path() -> Path:
    return settings.data_path / "security" / "rotation_state.json"


def _fallback_vault_path() -> Path:
    return settings.data_path / "security" / "local_vault.json"


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_keyring_get(key: str) -> str | None:
    try:
        return get_secret(key)
    except Exception:
        return None


def _safe_keyring_set(key: str, value: str) -> bool:
    try:
        set_secret(key, value)
        return True
    except Exception:
        return False


def get_vault_secret(key: str) -> str | None:
    keyring_value = _safe_keyring_get(key)
    if keyring_value:
        return keyring_value
    fallback = _read_json_file(_fallback_vault_path())
    value = fallback.get(key)
    return str(value) if isinstance(value, str) and value else None


def set_vault_secret(key: str, value: str) -> None:
    if _safe_keyring_set(key, value):
        return
    fallback_path = _fallback_vault_path()
    fallback = _read_json_file(fallback_path)
    fallback[key] = value
    _write_json_file(fallback_path, fallback)


def get_or_create_vault_secret(key: str, nbytes: int = 32) -> str:
    existing = get_vault_secret(key)
    if existing:
        return existing
    generated = secrets.token_hex(max(16, nbytes))
    set_vault_secret(key, generated)
    return generated


def rotate_secret_if_due(current_key: str, previous_key: str | None, period_seconds: int) -> bool:
    current_value = get_or_create_vault_secret(current_key)
    if period_seconds <= 0:
        return False

    state_path = _rotation_state_path()
    state = _read_json_file(state_path)
    now = datetime.now(timezone.utc)
    last_rotated_raw = state.get(current_key)
    if isinstance(last_rotated_raw, str):
        try:
            last_rotated = datetime.fromisoformat(last_rotated_raw)
            if last_rotated.tzinfo is None:
                last_rotated = last_rotated.replace(tzinfo=timezone.utc)
        except ValueError:
            last_rotated = now
    else:
        last_rotated = now

    age_seconds = (now - last_rotated).total_seconds()
    if age_seconds < period_seconds:
        if current_key not in state:
            state[current_key] = now.isoformat()
            _write_json_file(state_path, state)
        return False

    if previous_key:
        set_vault_secret(previous_key, current_value)
    new_value = secrets.token_hex(32)
    set_vault_secret(current_key, new_value)
    state[current_key] = now.isoformat()
    _write_json_file(state_path, state)
    return True
