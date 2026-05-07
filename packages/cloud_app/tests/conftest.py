"""Test fixtures.

SOLID-D in action: production code accepts pool/client Protocols; tests build
real instances via testcontainers and inject them. No mocks at this layer.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

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


JWT_SECRET = "testsecret-32-chars-minimum-padding-pls"


@pytest_asyncio.fixture
async def app(pg_pool):
    return create_app(pool=pg_pool, jwt_secret=JWT_SECRET)


@pytest_asyncio.fixture
async def api_client(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://test") as client:
        yield client


@dataclass(frozen=True)
class SeededAdmin:
    id: str
    email: str


@pytest_asyncio.fixture
async def seed_admin(pg_pool):
    """Seed an organisation + admin user."""
    org_id = uuid4()
    user_id = uuid4()
    async with pg_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO app.organisation (id, name, slug) VALUES ($1, $2, $3)",
            org_id, "Test Org", "test-org",
        )
        await conn.execute(
            """INSERT INTO app.users
                 (id, organisation_id, email, display_name, password_hash, tier, role)
               VALUES ($1, $2, $3, 'Test Admin', $4, 'operations', 'admin')""",
            user_id, org_id, "admin@test.example.com", hash_password("hunter2"),
        )
    return SeededAdmin(id=str(user_id), email="admin@test.example.com")


@pytest_asyncio.fixture
async def admin_token(seed_admin):
    return issue_token(
        JwtPayload(sub=seed_admin.id, tier="operations", role="admin"),
        secret=JWT_SECRET, lifetime=timedelta(hours=1),
    )


@dataclass(frozen=True)
class SeededSite:
    id: str
    slug: str


@dataclass(frozen=True)
class SeededDevice:
    id: str
    name: str


@pytest_asyncio.fixture
async def seed_site(pg_pool, seed_admin):
    site_id = uuid4()
    async with pg_pool.acquire() as conn:
        org_id = await conn.fetchval(
            "SELECT id FROM app.organisation WHERE slug = 'test-org'"
        )
        await conn.execute(
            """INSERT INTO app.site
                 (id, organisation_id, name, slug, mqtt_username, mqtt_password)
               VALUES ($1, $2, 'Bench', 'bench', 'solamon-bench', 'p')""",
            site_id, org_id,
        )
        await conn.execute(
            """INSERT INTO app.site_access (user_id, site_id, access_level)
               VALUES ($1, $2, 'admin')""",
            UUID(seed_admin.id), site_id,
        )
    return SeededSite(id=str(site_id), slug="bench")


@pytest_asyncio.fixture
async def seed_device_type(pg_pool):
    type_id = uuid4()
    async with pg_pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO app.device_type
                 (id, manufacturer, model, category, profile_slug, profile_yaml)
               VALUES ($1, 'AccuEnergy', 'Acuvim L', 'meter', 'acuvim_l', '{}'::jsonb)
               ON CONFLICT (profile_slug) DO UPDATE SET id = EXCLUDED.id""",
            type_id,
        )
        # Fetch the actual ID in case it was already present
        actual_id = await conn.fetchval(
            "SELECT id FROM app.device_type WHERE profile_slug = 'acuvim_l'"
        )
    return actual_id


@pytest_asyncio.fixture
async def seed_device(pg_pool, seed_site, seed_device_type):
    device_id = uuid4()
    async with pg_pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO app.device
                 (id, site_id, device_type_id, name, host, port, unit_id)
               VALUES ($1, $2, $3, 'M1', '192.168.1.254', 502, 1)""",
            device_id, UUID(seed_site.id), seed_device_type,
        )
    return SeededDevice(id=str(device_id), name="M1")
