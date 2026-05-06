"""Run the committed migration against a real Postgres and verify the schema."""
import pytest


@pytest.mark.asyncio
async def test_migration_creates_app_and_timeseries_schemas(pg_pool):
    async with pg_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name IN ('app', 'timeseries')"
        )
    schemas = {r["schema_name"] for r in rows}
    assert schemas == {"app", "timeseries"}


@pytest.mark.asyncio
async def test_migration_creates_reading_hypertable(pg_pool):
    """timescaledb_information.hypertables shows the registered hypertables."""
    async with pg_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT hypertable_schema, hypertable_name "
            "FROM timescaledb_information.hypertables"
        )
    pairs = {(r["hypertable_schema"], r["hypertable_name"]) for r in rows}
    assert ("timeseries", "reading") in pairs


@pytest.mark.asyncio
async def test_migration_is_idempotent(pg_pool, run_migrations_fn):
    """Re-running the migration on an already-migrated DB must succeed."""
    await run_migrations_fn()                # second time
    async with pg_pool.acquire() as conn:
        count = await conn.fetchval("SELECT count(*) FROM app.schema_migrations")
    assert count == 1
