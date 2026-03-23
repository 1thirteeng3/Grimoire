import keyring


SERVICE_NAME = "grimoire"


def set_secret(key: str, value: str) -> None:
    keyring.set_password(SERVICE_NAME, key, value)


def get_secret(key: str) -> str | None:
    return keyring.get_password(SERVICE_NAME, key)
