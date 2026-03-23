from app.core.secrets import get_secret, set_secret
from app.rag.shadowing import has_dangerous_command


def test_secrets_keyring_wrapper(monkeypatch):
    storage: dict[tuple[str, str], str] = {}

    def fake_set_password(service: str, key: str, value: str):
        storage[(service, key)] = value

    def fake_get_password(service: str, key: str):
        return storage.get((service, key))

    monkeypatch.setattr("app.core.secrets.keyring.set_password", fake_set_password)
    monkeypatch.setattr("app.core.secrets.keyring.get_password", fake_get_password)

    set_secret("api_key", "secret-value")
    assert get_secret("api_key") == "secret-value"


def test_shadowing_patterns():
    assert has_dangerous_command("rm -rf /tmp/foo") is True
    assert has_dangerous_command("list files only") is False
