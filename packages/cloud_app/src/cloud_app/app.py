"""FastAPI app factory.

The factory accepts the concrete pool + secret as parameters — never reads them
from os.environ. The composition root in __main__.py builds the pool + reads
env once, then calls create_app(...). Tests build their own app per fixture.
"""
from __future__ import annotations

import asyncpg
from fastapi import FastAPI

from .api.auth import router as auth_router
from .api.devices import router as devices_router
from .api.sites import router as sites_router


def create_app(*, pool: asyncpg.Pool, jwt_secret: str) -> FastAPI:
    app = FastAPI(title="Solamon Cloud API", version="0.1.0", root_path="")
    app.state.pool = pool
    app.state.jwt_secret = jwt_secret

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(sites_router, prefix="/api/v1")
    app.include_router(devices_router, prefix="/api/v1")

    return app
