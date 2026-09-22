"""Auth dependency + token extraction for the FastAPI app.

Bearer-token auth with the token resolved through ``auth_store``. The
``/health`` and root endpoints stay public so the frontend engine probe and
monitoring keep working unauthenticated.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend import auth_store

_bearer_scheme = HTTPBearer(auto_error=False)


def _extract_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
) -> str:
    """Bearer header first; query param ``token`` for WebSocket handshakes."""
    if credentials and credentials.credentials:
        return credentials.credentials
    token = request.query_params.get("token")
    if token:
        return token
    return ""


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict:
    """Return the authenticated user or raise 401 with a stable error shape."""
    token = _extract_token(request, credentials)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to continue.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = auth_store.resolve_token(token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid. Sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict | None:
    """Like get_current_user but returns None instead of raising."""
    token = _extract_token(request, credentials)
    if not token:
        return None
    return auth_store.resolve_token(token)
