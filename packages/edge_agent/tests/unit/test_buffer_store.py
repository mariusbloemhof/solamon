from datetime import UTC, datetime, timedelta

import pytest

from edge_agent.buffer.store import Buffer, ReadingRow, rotate_once


@pytest.mark.asyncio
async def test_buffer_deduplicates_and_marks_published(tmp_path):
    buffer = Buffer(tmp_path / "buffer.sqlite3")
    await buffer.init()
    now = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    row = ReadingRow(now, "device-1", "frequency_hz", "realtime", 50.02, None)

    await buffer.write_batch([row, row])
    rows = await buffer.fetch_unpublished()
    assert len(rows) == 1

    await buffer.mark_published([rows[0].id])
    assert await buffer.fetch_unpublished() == []


@pytest.mark.asyncio
async def test_buffer_depth_and_rotation(tmp_path):
    buffer = Buffer(tmp_path / "buffer.sqlite3")
    await buffer.init()
    old = (datetime.now(UTC) - timedelta(days=8)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    recent = (datetime.now(UTC) - timedelta(seconds=120)).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    await buffer.write_batch(
        [
            ReadingRow(old, "device-1", "frequency_hz", "realtime", 49.9, None),
            ReadingRow(recent, "device-1", "voltage_l1_n", "realtime", 230.0, None),
        ]
    )

    assert await buffer.compute_buffer_depth_seconds() > 100
    assert await rotate_once(buffer) == 1
    rows = await buffer.fetch_unpublished()
    assert [row.logical_metric_key for row in rows] == ["voltage_l1_n"]


@pytest.mark.asyncio
async def test_processed_command_ack_survives_new_buffer_instance(tmp_path):
    path = tmp_path / "buffer.sqlite3"
    buffer = Buffer(path)
    await buffer.init()
    expires = (datetime.now(UTC) + timedelta(minutes=5)).isoformat(timespec="milliseconds").replace(
        "+00:00",
        "Z",
    )
    ack = {"id": "cmd-1", "status": "confirmed"}

    await buffer.record_processed_command(command_id="cmd-1", expires_at=expires, ack=ack)

    restarted = Buffer(path)
    await restarted.init()
    assert await restarted.get_processed_command_ack("cmd-1") == ack
