"""Auth endpoints: /auth/login, /auth/me, /auth/logout."""
from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import asyncpg
from fastapi import APIRouter, HTTPException, Request

from ..auth.deps import CurrentUser
from ..auth.jwt import JwtPayload, issue_token
from ..auth.passwords import verify_password
from ..models.pydantic import LoginRequest, LoginResponse, User

router = APIRouter(prefix="/auth", tags=["auth"])

LIFETIME = timedelta(hours=24)


@router.post("/login", response_model=LoginResponse, operation_id="login")
async def login(request: Request, body: LoginRequest) -> LoginResponse:
    pool: asyncpg.Pool = request.app.state.pool
    secret: str = request.app.state.jwt_secret
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT id, email, display_name, password_hash, tier, role
               FROM app.users WHERE email = $1 AND is_active = true""",
            body.email,
        )
    if row is None or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(401, "Email or password incorrect")
    payload = JwtPayload(sub=str(row["id"]), tier=row["tier"], role=row["role"])
    token = issue_token(payload, secret=secret, lifetime=LIFETIME)
    user = User(id=row["id"], email=row["email"], display_name=row["display_name"],
                tier=row["tier"], role=row["role"])
    return LoginResponse(access_token=token, expires_in=int(LIFETIME.total_seconds()), user=user)


@router.post("/logout", status_code=204, operation_id="logout")
async def logout() -> None:
    """No-op in MVP — JWT is stateless. NextAuth clears its cookie client-side."""
    return None


@router.get("/me", response_model=User, operation_id="getCurrentUser")
async def me(user: CurrentUser) -> User:
    return user
