"""JWT issue/verify — pure functions."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

import jwt as pyjwt


@dataclass(frozen=True)
class JwtPayload:
    sub: str
    tier: Literal["operations", "client"]
    role: Literal["admin", "operator", "viewer", "billing"]


def issue_token(payload: JwtPayload, *, secret: str, lifetime: timedelta) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        **asdict(payload),
        "iat": int(now.timestamp()),
        "exp": int((now + lifetime).timestamp()),
    }
    return pyjwt.encode(claims, secret, algorithm="HS256")


def verify_token(token: str, *, secret: str) -> JwtPayload:
    claims = pyjwt.decode(token, secret, algorithms=["HS256"])
    return JwtPayload(sub=claims["sub"], tier=claims["tier"], role=claims["role"])
