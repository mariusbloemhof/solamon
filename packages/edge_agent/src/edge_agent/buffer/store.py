"""SQLite-backed reading buffer."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import aiosqlite

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
            await db.executemany(
                """INSERT OR IGNORE INTO reading_buffer
                   (time, device_id, logical_metric_key, block_name, value, raw_value, quality)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                payload,
            )
            await db.commit()

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


async def rotate_once(buffer: Buffer, max_age: timedelta = timedelta(days=7)) -> int:
    return await buffer.delete_older_than(datetime.now(UTC) - max_age)
