"""Single-user auth: static bearer token, or a Tailscale Serve identity header
that matches TAILSCALE_OWNER_LOGIN, or unauthenticated only when no token is
set (local dev). The server binds to 127.0.0.1 either way."""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, Query

from hq.config import settings


async def require_auth(
    authorization: str | None = Header(default=None),
    tailscale_user_login: str | None = Header(default=None),
    token_query: str | None = Query(default=None, alias="token"),
) -> None:
    """Accept the token as ``Authorization: Bearer <token>`` or as ``?token=<token>``.

    The query form exists only because the browser EventSource API cannot set
    request headers. Use it only for the SSE stream (``/api/events``) over HTTPS;
    a query string is logged by proxies, so never send it over plain HTTP.
    """
    s = settings()
    token = s.api_bearer_token
    if not token:
        return  # dev mode: no token configured, localhost-only bind is the boundary
    if tailscale_user_login and s.tailscale_owner_login:  # noqa: SIM102
        # Kept nested: a wrong login must fall through to the 401 below.
        if secrets.compare_digest(tailscale_user_login, s.tailscale_owner_login):
            return
    if authorization and authorization.startswith("Bearer "):  # noqa: SIM102
        # Kept nested: a wrong token must fall through to the 401 below.
        if secrets.compare_digest(authorization.removeprefix("Bearer "), token):
            return
    if token_query is not None and secrets.compare_digest(token_query, token):
        return
    raise HTTPException(status_code=401, detail="unauthorized")
