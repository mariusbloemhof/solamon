"""Migration runner — applies SQL files from packages/cloud_app/migrations/."""
from __future__ import annotations

from pathlib import Path

import asyncpg

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"   # packages/cloud_app/migrations/


async def run_migrations(pool: asyncpg.Pool, migrations_dir: Path | None = None) -> None:
    """Apply every *.sql file in lexical order. Each migration is wrapped in
    its own transaction; the migration file owns idempotency via IF NOT EXISTS."""
    base = migrations_dir or MIGRATIONS_DIR
    files = sorted(base.glob("[0-9]*.sql"))
    for sql_file in files:
        sql = sql_file.read_text(encoding="utf-8")
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(sql)
