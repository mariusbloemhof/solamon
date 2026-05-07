"""FastAPI auth dependencies. SOLID-D: routers depend on `current_user(...)`,
not on JWT or DB primitives directly."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .jwt import JwtPayload, verify_token
from ..models.pydantic import User

bearer_scheme = HTTPBearer(auto_error=False)


async def current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None:
        raise HTTPException(401, "missing bearer token")
    secret: str = request.app.state.jwt_secret
    pool: asyncpg.Pool = request.app.state.pool
    try:
        payload: JwtPayload = verify_token(credentials.credentials, secret=secret)
    except Exception:
        raise HTTPException(401, "invalid token")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, display_name, tier, role FROM app.users WHERE id = $1",
            UUID(payload.sub),
        )
    if row is None:
        raise HTTPException(401, "user not found")
    return User(**dict(row))


CurrentUser = Annotated[User, Depends(current_user)]
