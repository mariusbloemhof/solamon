"""Postgres connection pool wrapper.

SOLID-D: domain code accepts a `Pool`-shaped object; tests inject testcontainers'
real pool, production injects asyncpg's. No code outside this module imports asyncpg.
"""
from __future__ import annotations

import json
from typing import Any, Protocol

import asyncpg


class Pool(Protocol):
    async def acquire(self) -> Any: ...
    async def close(self) -> None: ...
    async def fetchval(self, query: str, *args: Any) -> Any: ...
    async def fetch(self, query: str, *args: Any) -> list: ...
    async def execute(self, query: str, *args: Any) -> str: ...


async def _init_connection(conn: asyncpg.Connection) -> None:
    # Decode jsonb columns to dict/list automatically. Without this asyncpg
    # returns jsonb as raw text and Pydantic fails to coerce dict[str, Any].
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


async def create_pool(database_url: str, **kwargs: Any) -> asyncpg.Pool:
    return await asyncpg.create_pool(database_url, init=_init_connection, **kwargs)
