"""Single-user auth: static bearer token, or requests arriving via Tailscale
Serve (identity header present), or unauthenticated only when no token is set
(local dev). The server binds to 127.0.0.1 either way."""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException

from hq.config import settings


async def require_auth(
    authorization: str | None = Header(default=None),
    tailscale_user_login: str | None = Header(default=None),
) -> None:
    token = settings().api_bearer_token
    if not token:
        return  # dev mode: no token configured, localhost-only bind is the boundary
    if tailscale_user_login:
        return
    if authorization and authorization.startswith("Bearer "):  # noqa: SIM102
        # Kept nested: a wrong token must fall through to the 401 below.
        if secrets.compare_digest(authorization.removeprefix("Bearer "), token):
            return
    raise HTTPException(status_code=401, detail="unauthorized")
