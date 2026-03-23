import os
from dataclasses import dataclass
from typing import Annotated, Callable
from urllib.parse import parse_qs, urlparse

from fastapi import Depends, HTTPException, WebSocket
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.security.secret_vault import get_or_create_vault_secret

security_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthPrincipal:
    subject: str
    scopes: frozenset[str]


ALL_SCOPES = frozenset(
    {
        "pacts:read",
        "pacts:write",
        "observability:read",
        "metrics:read",
        "ws:connect",
        "ws:write",
    }
)

OBSERVER_SCOPES = frozenset({"pacts:read", "observability:read", "metrics:read"})
ADMIN_SCOPES = ALL_SCOPES

_dev_principal = AuthPrincipal(subject="dev-bypass", scopes=ALL_SCOPES)


def _token_registry() -> dict[str, AuthPrincipal]:
    admin_override = os.getenv("GRIMOIRE_AUTH_ADMIN_TOKEN", "").strip()
    observer_override = os.getenv("GRIMOIRE_AUTH_OBSERVER_TOKEN", "").strip()
    admin_token = admin_override or get_or_create_vault_secret(
        settings.auth_admin_token_vault_key,
        nbytes=settings.auth_token_nbytes,
    )
    observer_token = observer_override or get_or_create_vault_secret(
        settings.auth_observer_token_vault_key,
        nbytes=settings.auth_token_nbytes,
    )
    return {
        admin_token: AuthPrincipal(subject="admin", scopes=ADMIN_SCOPES),
        observer_token: AuthPrincipal(subject="observer", scopes=OBSERVER_SCOPES),
    }


def setup_auth_tokens() -> None:
    if not settings.auth_required:
        return
    _token_registry()


def _resolve_principal(token: str | None) -> AuthPrincipal:
    if not settings.auth_required:
        return _dev_principal
    if not token:
        raise HTTPException(status_code=401, detail="AUTH_TOKEN_MISSING")
    registry = _token_registry()
    principal = registry.get(token)
    if principal is None:
        raise HTTPException(status_code=401, detail="AUTH_TOKEN_INVALID")
    return principal


def _ensure_scopes(principal: AuthPrincipal, required_scopes: set[str]) -> None:
    if not required_scopes.issubset(principal.scopes):
        raise HTTPException(status_code=403, detail="AUTH_SCOPE_FORBIDDEN")


def require_scopes_dep(*scopes: str) -> Callable:
    required_scopes = set(scopes)

    async def _dependency(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security_scheme)],
    ) -> AuthPrincipal:
        token = credentials.credentials if credentials else None
        principal = _resolve_principal(token)
        _ensure_scopes(principal, required_scopes)
        return principal

    return _dependency


async def maybe_require_metrics_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security_scheme)],
) -> AuthPrincipal | None:
    if not (settings.auth_required and settings.metrics_require_auth):
        return None
    token = credentials.credentials if credentials else None
    principal = _resolve_principal(token)
    _ensure_scopes(principal, {"metrics:read"})
    return principal


def _websocket_token_from_url(websocket: WebSocket) -> str | None:
    query = parse_qs(urlparse(str(websocket.url)).query)
    token_values = query.get("token", [])
    if token_values and token_values[0].strip():
        return token_values[0].strip()
    return None


async def authorize_websocket_connect(websocket: WebSocket) -> AuthPrincipal | None:
    if not settings.auth_required:
        return _dev_principal

    auth_header = websocket.headers.get("authorization", "").strip()
    header_token = None
    if auth_header.lower().startswith("bearer "):
        header_token = auth_header.split(" ", 1)[1].strip()
    query_token = _websocket_token_from_url(websocket)
    token = header_token or query_token
    try:
        principal = _resolve_principal(token)
        _ensure_scopes(principal, {"ws:connect"})
        return principal
    except HTTPException:
        await websocket.close(code=1008, reason="AUTH_REQUIRED")
        return None


def authorize_ws_message_type(principal: AuthPrincipal, message_type: str) -> bool:
    if message_type in {"INTENT_SUBMIT", "PACT_RESOLVE"}:
        return "ws:write" in principal.scopes
    return True
