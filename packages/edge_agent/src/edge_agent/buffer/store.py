"""SQLite-backed reading buffer."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import aiosqlite
import structlog

log = structlog.get_logger()

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS reading_buffer (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time TEXT NOT NULL,
    device_id TEXT NOT NULL,
    logical_metric_key TEXT NOT NULL,
    block_name TEXT NOT NULL,
    value REAL,
    raw_value INTEGER,
    quality TEXT NOT NULL DEFAULT 'good',
    published INTEGER NOT NULL DEFAULT 0,
    UNIQUE (time, device_id, logical_metric_key, block_name)
);

CREATE INDEX IF NOT EXISTS idx_buffer_unpublished
    ON reading_buffer (published, time)
    WHERE published = 0;

CREATE TABLE IF NOT EXISTS processed_commands (
    command_id TEXT PRIMARY KEY,
    expires_at TEXT NOT NULL,
    ack_json TEXT NOT NULL,
    processed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_processed_commands_expires
    ON processed_commands (expires_at);
"""


@dataclass(frozen=True)
class BufferRow:
    id: int
    time: str
    device_id: str
    logical_metric_key: str
    block_name: str
    value: float | int | str | None
    raw_value: int | None
    quality: Literal["good", "uncertain", "bad"]


@dataclass(frozen=True)
class ReadingRow:
    time: str
    device_id: str
    logical_metric_key: str
    block_name: str
    value: float | int | str | None
    raw_value: int | None
    quality: Literal["good", "uncertain", "bad"] = "good"


class Buffer:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    async def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.executescript(SCHEMA_SQL)
            await db.commit()

    async def write_batch(self, rows: Iterable[ReadingRow]) -> None:
        payload = [
            (
                row.time,
                row.device_id,
                row.logical_metric_key,
                row.block_name,
                row.value,
                row.raw_value,
                row.quality,
            )
            for row in rows
        ]
        if not payload:
            return
        async with aiosqlite.connect(self.path) as db:
            before = db.total_changes
            await db.executemany(
                """INSERT OR IGNORE INTO reading_buffer
                   (time, device_id, logical_metric_key, block_name, value, raw_value, quality)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                payload,
            )
            await db.commit()
            inserted = db.total_changes - before
        if inserted != len(payload):
            log.warning(
                "buffer.write_collision",
                attempted=len(payload),
                inserted=inserted,
                ignored=len(payload) - inserted,
            )

    async def fetch_unpublished(self, limit: int = 200) -> list[BufferRow]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT id, time, device_id, logical_metric_key, block_name, value, raw_value, quality
                   FROM reading_buffer
                   WHERE published = 0
                   ORDER BY time ASC, id ASC
                   LIMIT ?""",
                (limit,),
            )
            rows = await cursor.fetchall()
        return [BufferRow(**dict(row)) for row in rows]

    async def mark_published(self, ids: list[int]) -> None:
        if not ids:
            return
        placeholders = ",".join("?" for _ in ids)
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                f"UPDATE reading_buffer SET published = 1 WHERE id IN ({placeholders})",
                ids,
            )
            await db.commit()

    async def compute_buffer_depth_seconds(self) -> int:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute("SELECT MIN(time) FROM reading_buffer WHERE published = 0")
            row = await cursor.fetchone()
        if row is None or row[0] is None:
            return 0
        oldest = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
        return max(0, int((datetime.now(UTC) - oldest).total_seconds()))

    async def delete_older_than(self, cutoff: datetime) -> int:
        cutoff_str = cutoff.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute("DELETE FROM reading_buffer WHERE time < ?", (cutoff_str,))
            await db.commit()
            return cursor.rowcount or 0

    async def get_processed_command_ack(self, command_id: str) -> dict | None:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """SELECT ack_json
                   FROM processed_commands
                   WHERE command_id = ?
                     AND expires_at >= ?""",
                (command_id, _utc_now()),
            )
            row = await cursor.fetchone()
        return json.loads(row[0]) if row else None

    async def record_processed_command(
        self,
        *,
        command_id: str,
        expires_at: str,
        ack: dict,
        grace: timedelta = timedelta(minutes=5),
    ) -> None:
        expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00")) + grace
        expires_str = expires.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO processed_commands
                   (command_id, expires_at, ack_json, processed_at)
                   VALUES (?, ?, ?, ?)""",
                (command_id, expires_str, json.dumps(ack), _utc_now()),
            )
            await db.commit()

    async def prune_processed_commands(self) -> int:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "DELETE FROM processed_commands WHERE expires_at < ?",
                (_utc_now(),),
            )
            await db.commit()
            return cursor.rowcount or 0


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


async def rotate_once(buffer: Buffer, max_age: timedelta = timedelta(days=7)) -> int:
    deleted_readings = await buffer.delete_older_than(datetime.now(UTC) - max_age)
    await buffer.prune_processed_commands()
    return deleted_readings
