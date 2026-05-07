"""Test fixtures.

SOLID-D in action: production code accepts pool/client Protocols; tests build
real instances via testcontainers and inject them. No mocks at this layer.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

import asyncpg
import httpx
import pytest_asyncio
from fastapi.testclient import TestClient
from testcontainers.postgres import PostgresContainer

from cloud_app.app import create_app
from cloud_app.auth.jwt import JwtPayload, issue_token
from cloud_app.auth.passwords import hash_password
from cloud_app.db.migrations import run_migrations


@pytest_asyncio.fixture(scope="session")
async def pg_container() -> AsyncIterator[PostgresContainer]:
    # Use the timescale image so create_hypertable() works in migrations.
    with PostgresContainer("timescale/timescaledb:2.26.4-pg16") as pg:
        pg.with_env("POSTGRES_DB", "solamon")
        pg.with_env("POSTGRES_USER", "solamon")
        yield pg


@pytest_asyncio.fixture
async def pg_pool(pg_container) -> AsyncIterator[asyncpg.Pool]:
    url = pg_container.get_connection_url().replace("postgresql+psycopg2", "postgresql")
    pool = await asyncpg.create_pool(url, min_size=1, max_size=5)
    yield pool
    await pool.close()


@pytest_asyncio.fixture(autouse=True)
async def _migrate(pg_pool):
    """Apply migrations once per test (idempotent)."""
    await run_migrations(pg_pool)
    # Truncate non-reference tables for test isolation.
    async with pg_pool.acquire() as conn:
        # Check if schemas exist before truncating
        schemas_exist = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = 'app')"
        )
        if schemas_exist:
            await conn.execute("""
                TRUNCATE
                    app.audit_entry, app.control_command, app.dead_letter,
                    app.device_snapshot, app.site_access, app.users,
                    app.device, app.site, app.organisation,
                    timeseries.reading
                RESTART IDENTITY CASCADE
            """)


@pytest_asyncio.fixture
async def run_migrations_fn(pg_pool):
    async def _run():
        await run_migrations(pg_pool)
    return _run
