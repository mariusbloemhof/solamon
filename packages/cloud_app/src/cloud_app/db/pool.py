"""Postgres connection pool wrapper.

SOLID-D: domain code accepts a `Pool`-shaped object; tests inject testcontainers'
real pool, production injects asyncpg's. No code outside this module imports asyncpg.
"""
from __future__ import annotations

from typing import Any, Protocol

import asyncpg


class Pool(Protocol):
    async def acquire(self) -> Any: ...
    async def close(self) -> None: ...
    async def fetchval(self, query: str, *args: Any) -> Any: ...
    async def fetch(self, query: str, *args: Any) -> list: ...
    async def execute(self, query: str, *args: Any) -> str: ...


async def create_pool(database_url: str, **kwargs: Any) -> asyncpg.Pool:
    return await asyncpg.create_pool(database_url, **kwargs)
