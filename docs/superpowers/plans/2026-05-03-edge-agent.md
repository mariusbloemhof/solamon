# Edge Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans.

**Goal:** Build the Pi-side edge agent: pulls site config from cloud once at startup, polls Modbus per profile, buffers locally in SQLite, publishes telemetry + heartbeat over MQTT, subscribes to control commands and writes them back with read-back verification.

**Architecture:** Single Python process. Five concurrent asyncio tasks (poller, publisher, heartbeat, command subscriber, buffer rotation) wired in `__main__.py`. All I/O goes through Protocols injected at the composition root: `ModbusClient` (real: pymodbus async TCP), `MqttClient` (real: asyncio-mqtt), `Buffer` (real: aiosqlite). The `profile_loader` package owns all profile parsing/decoding/fingerprint logic.

**Tech Stack:** Python 3.12, pymodbus 3.x, asyncio-mqtt, aiosqlite, structlog, httpx (for /edge/config bootstrap).

**Linear:** SOL-7.

**Conventions:** [`2026-05-03-conventions.md`](2026-05-03-conventions.md).

**Spec source of truth:**
- [`docs/specs/edge-agent/architecture.md`](../../specs/edge-agent/architecture.md)
- [`docs/specs/edge-agent/config-loader.md`](../../specs/edge-agent/config-loader.md)
- [`docs/specs/edge-agent/modbus-poller.md`](../../specs/edge-agent/modbus-poller.md)
- [`docs/specs/edge-agent/mqtt-publisher.md`](../../specs/edge-agent/mqtt-publisher.md)
- [`docs/specs/edge-agent/command-subscriber.md`](../../specs/edge-agent/command-subscriber.md)

**Depends on:** `packages/profile_loader/` (path dep). Cloud spec (this plan tests against the MQTT contracts from `cloud/mqtt-contracts.md` but doesn't need a running cloud; tests use a fake broker).

---

## File structure

```
packages/edge_agent/
├── pyproject.toml
├── Dockerfile                                    # ARM64; produces solamon-edge-agent
├── src/edge_agent/
│   ├── __init__.py
│   ├── __main__.py                               # composition root
│   ├── config/
│   │   ├── __init__.py
│   │   ├── bootstrap.py                          # /etc/solamon/bootstrap.yaml loader
│   │   └── site_config.py                        # fetch + cache /api/v1/edge/config
│   ├── buffer/
│   │   ├── __init__.py
│   │   ├── schema.py                             # CREATE TABLE statements
│   │   ├── store.py                              # aiosqlite-backed buffer (Protocol + impl)
│   │   └── rotation.py                           # ring delete > 7 days
│   ├── modbus/
│   │   ├── __init__.py
│   │   ├── poller.py                             # ModbusPoller — uses Profile.schedule + decode
│   │   └── client.py                             # Protocol matching pymodbus surface
│   ├── mqtt/
│   │   ├── __init__.py
│   │   ├── client.py                             # asyncio-mqtt wrapper + Protocol + LWT
│   │   ├── publisher.py                          # drains buffer → MQTT publish
│   │   ├── heartbeat.py                          # 60-s heartbeat publish
│   │   └── command_subscriber.py                 # consume commands, write+readback, ack
│   ├── metrics.py                                # in-process counters: modbus_errors, halted_blocks
│   └── now.py                                    # now_utc() helper (RFC 3339 with ms)
└── tests/
    ├── conftest.py
    ├── unit/
    │   ├── test_now_utc.py
    │   ├── test_bootstrap_config.py
    │   ├── test_buffer_store.py
    │   ├── test_buffer_rotation.py
    │   ├── test_metrics.py
    │   ├── test_publish_payload_shape.py
    │   └── test_command_validation.py
    └── integration/
        ├── test_site_config_fetch.py             # uses pytest httpserver
        ├── test_modbus_poller.py                 # fake ModbusClient
        ├── test_mqtt_publisher.py                # CapturingMqtt fake
        └── test_command_subscriber_round_trip.py # write + readback + ack
```

`profile_loader` is THE source-of-truth for catalog/profile parsing. The edge agent never duplicates that logic.

---

## Task 1: Package skeleton + `now_utc` helper

**Files:**
- Create: `packages/edge_agent/pyproject.toml`
- Create: `packages/edge_agent/src/edge_agent/__init__.py`
- Create: `packages/edge_agent/src/edge_agent/now.py`
(No `__init__.py` files in `tests/` per [conventions §7.9](2026-05-03-conventions.md).)
- Create: `packages/edge_agent/tests/unit/test_now_utc.py`

- [ ] **Step 1: Failing test**

```python
# packages/edge_agent/tests/unit/test_now_utc.py
"""now_utc must produce RFC 3339 strings with ms precision and Z suffix.

Spec: cloud/mqtt-contracts.md §3 — 'all timestamps RFC 3339 / ISO 8601 with
millisecond precision and explicit UTC offset (Z)'.
"""
import re

from edge_agent.now import now_utc

ISO_MS_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def test_now_utc_format():
    s = now_utc()
    assert ISO_MS_Z.match(s), f"got {s!r}"


def test_now_utc_returns_utc_not_local():
    """A subtle but real bug: datetime.now() (without tz) + appending 'Z' produces
    a malformed string that asserts UTC while carrying local time. Guard against it."""
    from datetime import datetime, timezone
    s = now_utc()
    parsed = datetime.fromisoformat(s.replace("Z", "+00:00"))
    delta = abs((parsed - datetime.now(timezone.utc)).total_seconds())
    assert delta < 5
```

- [ ] **Step 2: Run** — fails.

- [ ] **Step 3: Implement**

`packages/edge_agent/pyproject.toml`:
```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "solamon-edge-agent"
version = "0.0.0"
requires-python = ">=3.12"
dependencies = [
    "solamon-profile-loader",
    "pymodbus>=3.6",
    "asyncio-mqtt>=0.16",
    "aiosqlite>=0.20",
    "httpx>=0.27",
    "pyyaml>=6.0",
    "structlog>=24.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-httpserver>=1.0",
    "ruff>=0.4",
]

[project.scripts]
solamon-edge-agent = "edge_agent.__main__:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.uv.sources]
solamon-profile-loader = { workspace = true }
```

```python
# packages/edge_agent/src/edge_agent/__init__.py
"""Solamon edge agent — Pi-side telemetry + control."""
__version__ = "0.0.0"
```

```python
# packages/edge_agent/src/edge_agent/now.py
"""now_utc — RFC 3339 with millisecond precision and 'Z'.

datetime.now() (without tz) + appending 'Z' produces a malformed string that
asserts UTC while carrying local time. ALWAYS use now_utc().
"""
from datetime import datetime, timezone


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
```

- [ ] **Step 4: Run + commit**

```bash
python -m pip install -e "packages/edge_agent[dev]"
python -m pytest packages/edge_agent/tests/unit/test_now_utc.py -v
git add packages/edge_agent/
git commit -m "feat(edge-agent): scaffold package + now_utc helper"
```

---

## Task 2: Bootstrap config loader

**Files:**
- Create: `packages/edge_agent/src/edge_agent/config/__init__.py`
- Create: `packages/edge_agent/src/edge_agent/config/bootstrap.py`
- Create: `packages/edge_agent/tests/unit/test_bootstrap_config.py`

- [ ] **Step 1: Failing test**

```python
# packages/edge_agent/tests/unit/test_bootstrap_config.py
from pathlib import Path

import pytest

from edge_agent.config.bootstrap import BootstrapConfig, load_bootstrap


def test_load_bootstrap_parses_required_fields(tmp_path: Path):
    p = tmp_path / "bootstrap.yaml"
    p.write_text(
        """
schema_version: "1.0"
site_slug: johansworkbench
cloud_url: https://cloud.example.com
bearer_token: super-secret
device_host: 192.168.1.254
device_unit_id: 1
log_level: INFO
""",
        encoding="utf-8",
    )
    cfg = load_bootstrap(p)
    assert isinstance(cfg, BootstrapConfig)
    assert cfg.site_slug == "johansworkbench"
    assert cfg.cloud_url == "https://cloud.example.com"
    assert cfg.bearer_token == "super-secret"
    assert cfg.device_host == "192.168.1.254"
    assert cfg.log_level == "INFO"


def test_load_bootstrap_rejects_missing_required_field(tmp_path: Path):
    p = tmp_path / "bootstrap.yaml"
    p.write_text(
        """
schema_version: "1.0"
site_slug: x
""",
        encoding="utf-8",
    )
    with pytest.raises(KeyError):
        load_bootstrap(p)


def test_bootstrap_config_is_frozen():
    cfg = BootstrapConfig(
        schema_version="1.0", site_slug="x", cloud_url="x",
        bearer_token="x", device_host="x", device_unit_id=1, log_level="INFO",
    )
    with pytest.raises(Exception):
        cfg.bearer_token = "leak"
```

- [ ] **Step 2: Implement**

```python
# packages/edge_agent/src/edge_agent/config/__init__.py
```

```python
# packages/edge_agent/src/edge_agent/config/bootstrap.py
"""Loads /etc/solamon/bootstrap.yaml — the per-site secret + cloud URL the
Pi installer wrote at install time. This is the FIRST thing the agent reads."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class BootstrapConfig:
    schema_version: str
    site_slug: str
    cloud_url: str
    bearer_token: str
    device_host: str
    device_unit_id: int
    log_level: str


def load_bootstrap(path: Path | str) -> BootstrapConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return BootstrapConfig(
        schema_version=raw["schema_version"],
        site_slug=raw["site_slug"],
        cloud_url=raw["cloud_url"],
        bearer_token=raw["bearer_token"],
        device_host=raw["device_host"],
        device_unit_id=int(raw.get("device_unit_id", 1)),
        log_level=raw.get("log_level", "INFO"),
    )
```

- [ ] **Step 3: Run + commit**

```bash
python -m pytest packages/edge_agent/tests/unit/test_bootstrap_config.py -v
git add packages/edge_agent/src/edge_agent/config/ packages/edge_agent/tests/unit/test_bootstrap_config.py
git commit -m "feat(edge-agent): bootstrap config loader (BootstrapConfig + load_bootstrap)"
```

---

## Task 3: Site config fetcher (calls /api/v1/edge/config)

**Files:**
- Create: `packages/edge_agent/src/edge_agent/config/site_config.py`
- Create: `packages/edge_agent/tests/integration/test_site_config_fetch.py`

- [ ] **Step 1: Failing test**

```python
# packages/edge_agent/tests/integration/test_site_config_fetch.py
"""Use pytest-httpserver to stand up a fake /api/v1/edge/config endpoint."""
import json
from pathlib import Path

import pytest

from edge_agent.config.site_config import SiteConfig, fetch_site_config, load_cached_site_config


SAMPLE = {
    "site": {"slug": "bench", "id": "00000000-0000-0000-0000-000000000001",
             "timezone": "Africa/Johannesburg", "name": "Bench"},
    "device": {"id": "00000000-0000-0000-0000-000000000002",
               "host": "192.168.1.254", "port": 502, "unit_id": 1,
               "profile_slug": "acuvim_l"},
    "profile": {"schema_version": "1.0",
                "device": {"manufacturer": "AccuEnergy", "model": "Acuvim L", "category": "meter"},
                "connection": {"protocol": "modbus_tcp", "default_port": 502, "default_unit_id": 1},
                "fingerprint": {"reads": []}, "read_blocks": []},
    "logical_metrics_catalog": {},
    "mqtt": {"broker_host": "cloud.example.com", "broker_port": 8883,
             "username": "solamon-bench", "password": "p",
             "client_id": "solamon-edge-bench", "topic_prefix": "solamon/bench"},
}


def test_fetch_site_config_returns_parsed(httpserver):
    httpserver.expect_request(
        "/api/v1/edge/config/bench",
        headers={"Authorization": "Bearer secret"},
    ).respond_with_json(SAMPLE)

    cfg = fetch_site_config(
        cloud_url=httpserver.url_for("").rstrip("/"),
        site_slug="bench", bearer_token="secret",
    )
    assert isinstance(cfg, SiteConfig)
    assert cfg.site_slug == "bench"
    assert cfg.mqtt.broker_host == "cloud.example.com"
    assert cfg.profile["device"]["manufacturer"] == "AccuEnergy"


def test_fetch_caches_to_disk_and_load_cached_round_trips(httpserver, tmp_path: Path):
    httpserver.expect_request("/api/v1/edge/config/bench").respond_with_json(SAMPLE)
    cache_path = tmp_path / "site_config.yaml"
    cfg1 = fetch_site_config(
        cloud_url=httpserver.url_for("").rstrip("/"),
        site_slug="bench", bearer_token="secret", cache_path=cache_path,
    )
    cfg2 = load_cached_site_config(cache_path)
    assert cfg2.site_slug == cfg1.site_slug
    assert cfg2.mqtt.client_id == cfg1.mqtt.client_id


def test_fetch_falls_back_to_cache_on_network_error(tmp_path: Path):
    cache_path = tmp_path / "site_config.yaml"
    cache_path.write_text(json.dumps(SAMPLE), encoding="utf-8")
    cfg = fetch_site_config(
        cloud_url="http://does-not-exist.invalid:1",
        site_slug="bench", bearer_token="secret",
        cache_path=cache_path, fallback_to_cache=True,
    )
    assert cfg.site_slug == "bench"
```

- [ ] **Step 2: Implement**

```python
# packages/edge_agent/src/edge_agent/config/site_config.py
"""Fetches /api/v1/edge/config/{slug} from the cloud. Caches to disk so the Pi
can boot offline if the cloud is unreachable."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import httpx


@dataclass(frozen=True)
class MqttSettings:
    broker_host: str
    broker_port: int
    username: str
    password: str
    client_id: str
    topic_prefix: str


@dataclass(frozen=True)
class SiteConfig:
    site_slug: str
    site_id: str
    site_timezone: str
    device_id: str
    device_host: str
    device_port: int
    device_unit_id: int
    profile_slug: str
    profile: dict
    catalog: dict
    mqtt: MqttSettings


def _from_payload(raw: dict) -> SiteConfig:
    return SiteConfig(
        site_slug=raw["site"]["slug"], site_id=raw["site"]["id"],
        site_timezone=raw["site"].get("timezone", "UTC"),
        device_id=raw["device"]["id"], device_host=raw["device"]["host"],
        device_port=int(raw["device"]["port"]), device_unit_id=int(raw["device"]["unit_id"]),
        profile_slug=raw["device"]["profile_slug"],
        profile=raw["profile"],
        catalog=raw["logical_metrics_catalog"],
        mqtt=MqttSettings(**raw["mqtt"]),
    )


def fetch_site_config(
    *, cloud_url: str, site_slug: str, bearer_token: str,
    cache_path: Path | None = None, fallback_to_cache: bool = False,
    timeout: float = 10.0,
) -> SiteConfig:
    """GETs /api/v1/edge/config/{slug}; on success, persists to cache_path."""
    url = f"{cloud_url.rstrip('/')}/api/v1/edge/config/{site_slug}"
    try:
        response = httpx.get(
            url, headers={"Authorization": f"Bearer {bearer_token}"}, timeout=timeout,
        )
        response.raise_for_status()
        raw = response.json()
        cfg = _from_payload(raw)
        if cache_path is not None:
            cache_path.write_text(json.dumps(raw), encoding="utf-8")
        return cfg
    except (httpx.HTTPError, httpx.HTTPStatusError) as e:
        if fallback_to_cache and cache_path is not None and cache_path.exists():
            return load_cached_site_config(cache_path)
        raise


def load_cached_site_config(path: Path) -> SiteConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return _from_payload(raw)
```

- [ ] **Step 3: Run + commit**

```bash
python -m pytest packages/edge_agent/tests/integration/test_site_config_fetch.py -v
git add packages/edge_agent/src/edge_agent/config/site_config.py packages/edge_agent/tests/integration/test_site_config_fetch.py
git commit -m "feat(edge-agent): site config fetcher with disk cache + offline fallback"
```

---

## Task 4: SQLite buffer (schema + store)

**Files:**
- Create: `packages/edge_agent/src/edge_agent/buffer/__init__.py`
- Create: `packages/edge_agent/src/edge_agent/buffer/schema.py`
- Create: `packages/edge_agent/src/edge_agent/buffer/store.py`
- Create: `packages/edge_agent/tests/unit/test_buffer_store.py`

- [ ] **Step 1: Failing test**

```python
# packages/edge_agent/tests/unit/test_buffer_store.py
from datetime import datetime, timezone
from pathlib import Path

import pytest

from edge_agent.buffer.store import Buffer


@pytest.mark.asyncio
async def test_insert_and_fetch_unpublished_round_trips(tmp_path: Path):
    db_path = tmp_path / "buffer.db"
    buf = Buffer(db_path)
    await buf.init()
    now = datetime.now(timezone.utc)
    await buf.insert_readings(
        block_name="realtime", time=now, device_id="dev-1",
        readings=[("frequency_hz", 50.02, "good"),
                  ("active_power_total", 12.35, "good")],
    )
    rows = await buf.fetch_unpublished(limit=10)
    assert len(rows) == 2
    assert {r.logical_metric_key for r in rows} == {"frequency_hz", "active_power_total"}


@pytest.mark.asyncio
async def test_mark_published_excludes_from_subsequent_fetch(tmp_path: Path):
    buf = Buffer(tmp_path / "b.db")
    await buf.init()
    now = datetime.now(timezone.utc)
    await buf.insert_readings(block_name="realtime", time=now, device_id="dev-1",
                              readings=[("frequency_hz", 50.02, "good")])
    rows = await buf.fetch_unpublished(limit=10)
    await buf.mark_published([r.id for r in rows])
    assert await buf.fetch_unpublished(limit=10) == []


@pytest.mark.asyncio
async def test_unique_constraint_dedups_on_block_time_metric(tmp_path: Path):
    buf = Buffer(tmp_path / "b.db")
    await buf.init()
    now = datetime.now(timezone.utc)
    await buf.insert_readings(block_name="realtime", time=now, device_id="dev-1",
                              readings=[("frequency_hz", 50.02, "good")])
    # Same key — should not duplicate
    await buf.insert_readings(block_name="realtime", time=now, device_id="dev-1",
                              readings=[("frequency_hz", 50.02, "good")])
    rows = await buf.fetch_unpublished(limit=10)
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_compute_buffer_depth_seconds(tmp_path: Path):
    """buffer_depth_seconds = oldest unpublished's age."""
    from datetime import timedelta
    buf = Buffer(tmp_path / "b.db")
    await buf.init()
    old = datetime.now(timezone.utc) - timedelta(seconds=120)
    await buf.insert_readings(block_name="realtime", time=old, device_id="dev-1",
                              readings=[("frequency_hz", 50.0, "good")])
    depth = await buf.compute_buffer_depth_seconds()
    assert depth >= 119
```

- [ ] **Step 2: Implement**

```python
# packages/edge_agent/src/edge_agent/buffer/schema.py
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS reading (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    block_name TEXT NOT NULL,
    time TEXT NOT NULL,                       -- ISO 8601 with ms + Z
    device_id TEXT NOT NULL,
    logical_metric_key TEXT NOT NULL,
    value REAL,
    quality TEXT NOT NULL CHECK (quality IN ('good','uncertain','bad')),
    published INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (time, device_id, logical_metric_key, block_name)
);

CREATE INDEX IF NOT EXISTS idx_reading_unpublished
    ON reading (published, time)
    WHERE published = 0;

CREATE INDEX IF NOT EXISTS idx_reading_age ON reading (time);
"""
```

```python
# packages/edge_agent/src/edge_agent/buffer/store.py
"""SQLite-backed reading buffer.

SOLID-D: domain code accepts a Buffer Protocol; tests + production use the
same impl with different paths (no in-memory mock needed — SQLite is fast).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import aiosqlite

from .schema import SCHEMA_SQL


@dataclass(frozen=True)
class BufferRow:
    id: int
    block_name: str
    time: datetime
    device_id: str
    logical_metric_key: str
    value: float | None
    quality: str


class Buffer:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    async def init(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.executescript(SCHEMA_SQL)
            await db.commit()

    async def insert_readings(
        self, *, block_name: str, time: datetime, device_id: str,
        readings: Iterable[tuple[str, float | None, str]],
    ) -> None:
        time_str = time.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        async with aiosqlite.connect(self._path) as db:
            await db.executemany(
                """INSERT OR IGNORE INTO reading
                     (block_name, time, device_id, logical_metric_key, value, quality)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [(block_name, time_str, device_id, k, v, q) for k, v, q in readings],
            )
            await db.commit()

    async def fetch_unpublished(self, *, limit: int = 200) -> list[BufferRow]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT id, block_name, time, device_id, logical_metric_key, value, quality
                   FROM reading WHERE published = 0
                   ORDER BY time ASC LIMIT ?""",
                (limit,),
            )
            rows = await cursor.fetchall()
        return [
            BufferRow(
                id=r["id"], block_name=r["block_name"],
                time=datetime.fromisoformat(r["time"].replace("Z", "+00:00")),
                device_id=r["device_id"], logical_metric_key=r["logical_metric_key"],
                value=r["value"], quality=r["quality"],
            )
            for r in rows
        ]

    async def mark_published(self, ids: list[int]) -> None:
        if not ids:
            return
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                f"UPDATE reading SET published = 1 WHERE id IN ({','.join('?' * len(ids))})",
                ids,
            )
            await db.commit()

    async def compute_buffer_depth_seconds(self) -> int:
        """Age of the oldest UNpublished row in seconds; 0 if buffer is drained."""
        async with aiosqlite.connect(self._path) as db:
            cursor = await db.execute(
                "SELECT MIN(time) FROM reading WHERE published = 0"
            )
            row = await cursor.fetchone()
        if row is None or row[0] is None:
            return 0
        oldest = datetime.fromisoformat(row[0].replace("Z", "+00:00"))
        from datetime import timezone
        return int((datetime.now(timezone.utc) - oldest).total_seconds())

    async def delete_older_than(self, cutoff: datetime) -> int:
        cutoff_str = cutoff.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        async with aiosqlite.connect(self._path) as db:
            cursor = await db.execute("DELETE FROM reading WHERE time < ?", (cutoff_str,))
            await db.commit()
            return cursor.rowcount or 0
```

- [ ] **Step 3: Run + commit**

```bash
python -m pytest packages/edge_agent/tests/unit/test_buffer_store.py -v
git add packages/edge_agent/src/edge_agent/buffer/ packages/edge_agent/tests/unit/test_buffer_store.py
git commit -m "feat(edge-agent): SQLite buffer (schema + store + dedup + buffer_depth)"
```

---

## Task 5: Buffer rotation task

**Files:**
- Create: `packages/edge_agent/src/edge_agent/buffer/rotation.py`
- Create: `packages/edge_agent/tests/unit/test_buffer_rotation.py`

- [ ] **Step 1: Failing test**

```python
# packages/edge_agent/tests/unit/test_buffer_rotation.py
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from edge_agent.buffer.rotation import rotate_once
from edge_agent.buffer.store import Buffer


@pytest.mark.asyncio
async def test_rotate_deletes_rows_older_than_cutoff(tmp_path: Path):
    buf = Buffer(tmp_path / "b.db")
    await buf.init()
    old = datetime.now(timezone.utc) - timedelta(days=8)
    fresh = datetime.now(timezone.utc) - timedelta(hours=1)
    await buf.insert_readings(block_name="realtime", time=old, device_id="d",
                              readings=[("frequency_hz", 49.9, "good")])
    await buf.insert_readings(block_name="realtime", time=fresh, device_id="d",
                              readings=[("frequency_hz", 50.0, "good")])
    deleted = await rotate_once(buf, max_age=timedelta(days=7))
    assert deleted == 1
    rows = await buf.fetch_unpublished(limit=10)
    assert len(rows) == 1                # only the fresh one survives
```

- [ ] **Step 2: Implement**

```python
# packages/edge_agent/src/edge_agent/buffer/rotation.py
"""Ring delete: drop reading rows older than max_age (default 7 days)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import structlog

from .store import Buffer

log = structlog.get_logger()


async def rotate_once(buffer: Buffer, *, max_age: timedelta = timedelta(days=7)) -> int:
    cutoff = datetime.now(timezone.utc) - max_age
    deleted = await buffer.delete_older_than(cutoff)
    if deleted:
        log.info("buffer.rotation", deleted_rows=deleted)
    return deleted


async def rotation_loop(buffer: Buffer, *, interval_s: float = 600.0,
                        max_age: timedelta = timedelta(days=7)) -> None:
    while True:
        try:
            await rotate_once(buffer, max_age=max_age)
        except Exception as e:
            log.error("buffer.rotation_failed", error=str(e))
        await asyncio.sleep(interval_s)
```

- [ ] **Step 3: Run + commit**

```bash
python -m pytest packages/edge_agent/tests/unit/test_buffer_rotation.py -v
git add packages/edge_agent/src/edge_agent/buffer/rotation.py packages/edge_agent/tests/unit/test_buffer_rotation.py
git commit -m "feat(edge-agent): buffer rotation (delete rows older than 7 days)"
```

---

## Task 6: In-process metrics counters

**Files:**
- Create: `packages/edge_agent/src/edge_agent/metrics.py`
- Create: `packages/edge_agent/tests/unit/test_metrics.py`

- [ ] **Step 1: Failing test**

```python
# packages/edge_agent/tests/unit/test_metrics.py
from datetime import datetime, timezone

from edge_agent.metrics import EdgeMetrics


def test_metrics_initial_state():
    m = EdgeMetrics()
    assert m.modbus_errors_per_minute_total() == 0.0
    assert m.last_modbus_success_iso() is None
    assert m.halted_blocks == set()


def test_record_modbus_error_increments():
    m = EdgeMetrics()
    m.record_modbus_error()
    m.record_modbus_error()
    # We've added 2 in this minute → expect ~2.0 / minute window
    assert m.modbus_errors_per_minute_total() >= 2.0


def test_record_modbus_success_sets_iso_timestamp():
    m = EdgeMetrics()
    m.record_modbus_success()
    iso = m.last_modbus_success_iso()
    assert iso is not None
    parsed = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None


def test_halt_unhalt_block():
    m = EdgeMetrics()
    m.halt_block("energy")
    assert "energy" in m.halted_blocks
    m.unhalt_block("energy")
    assert "energy" not in m.halted_blocks
```

- [ ] **Step 2: Implement**

```python
# packages/edge_agent/src/edge_agent/metrics.py
"""In-process counters for the heartbeat payload.

SOLID-S: this is the only place mutable in-process metric state lives.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone

from .now import now_utc


class EdgeMetrics:
    """One instance per agent process. Mutated by poller / publisher; read by heartbeat."""

    def __init__(self) -> None:
        self._modbus_errors: deque[datetime] = deque()
        self._last_modbus_success: datetime | None = None
        self.halted_blocks: set[str] = set()

    def record_modbus_error(self) -> None:
        self._modbus_errors.append(datetime.now(timezone.utc))
        self._evict_old_errors()

    def record_modbus_success(self) -> None:
        self._last_modbus_success = datetime.now(timezone.utc)

    def modbus_errors_per_minute_total(self) -> float:
        self._evict_old_errors()
        return float(len(self._modbus_errors))

    def last_modbus_success_iso(self) -> str | None:
        if self._last_modbus_success is None:
            return None
        return self._last_modbus_success.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def halt_block(self, block_name: str) -> None:
        self.halted_blocks.add(block_name)

    def unhalt_block(self, block_name: str) -> None:
        self.halted_blocks.discard(block_name)

    def _evict_old_errors(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=1)
        while self._modbus_errors and self._modbus_errors[0] < cutoff:
            self._modbus_errors.popleft()
```

- [ ] **Step 3: Run + commit**

```bash
python -m pytest packages/edge_agent/tests/unit/test_metrics.py -v
git add packages/edge_agent/src/edge_agent/metrics.py packages/edge_agent/tests/unit/test_metrics.py
git commit -m "feat(edge-agent): EdgeMetrics counters (errors/min + halted_blocks)"
```

---

## Task 7: Modbus poller (uses profile_loader)

**Files:**
- Create: `packages/edge_agent/src/edge_agent/modbus/__init__.py`
- Create: `packages/edge_agent/src/edge_agent/modbus/client.py`
- Create: `packages/edge_agent/src/edge_agent/modbus/poller.py`
- Create: `packages/edge_agent/tests/integration/test_modbus_poller.py`

- [ ] **Step 1: Failing test**

```python
# packages/edge_agent/tests/integration/test_modbus_poller.py
"""Drive the poller end-to-end with a fake ModbusClient that returns canned responses."""
import asyncio
import struct
from pathlib import Path
from typing import Any

import pytest

from edge_agent.buffer.store import Buffer
from edge_agent.metrics import EdgeMetrics
from edge_agent.modbus.poller import poll_block_once
from profile_loader import ProfileLoader


REPO_ROOT = Path(__file__).resolve().parents[5]
ARCH = REPO_ROOT / "architecture"


class FakeResponse:
    def __init__(self, registers: list[int]):
        self.registers = registers
    def isError(self): return False


class FakeModbus:
    """Returns canned big-endian 16-bit register lists."""
    def __init__(self, responses: dict[tuple[int, int], list[int]]):
        self.responses = responses
        self.calls: list[tuple[int, int]] = []

    async def read_holding_registers(self, address: int, count: int, slave: int = 1):
        self.calls.append((address, count))
        return FakeResponse(self.responses.get((address, count), [0] * count))


@pytest.fixture
def loaded_profile_and_catalog():
    loader = ProfileLoader()
    catalog = loader.load_catalog(ARCH / "logical_metrics.yaml")
    profile = loader.load_profile(ARCH / "profiles" / "acuvim_l.yaml", catalog)
    return profile, catalog, loader.decoders


@pytest.mark.asyncio
async def test_poll_block_once_writes_to_buffer(loaded_profile_and_catalog, tmp_path):
    profile, catalog, decoders = loaded_profile_and_catalog
    realtime = next(b for b in profile.read_blocks if b.name == "realtime")

    # Build a real Modbus response for the realtime block.
    payload = bytearray(realtime.length * 2)
    f = next(m for m in realtime.metrics if m.logical == "frequency_hz")
    struct.pack_into(">f", payload, f.offset, 50.02)
    registers = [
        int.from_bytes(payload[i:i + 2], "big") for i in range(0, len(payload), 2)
    ]
    client = FakeModbus({(realtime.address, realtime.length): registers})

    buffer = Buffer(tmp_path / "b.db")
    await buffer.init()
    metrics = EdgeMetrics()

    await poll_block_once(
        client=client, profile=profile, catalog=catalog, decoders=decoders,
        block=realtime, device_id="dev-1", unit_id=1,
        buffer=buffer, metrics=metrics,
    )

    rows = await buffer.fetch_unpublished(limit=100)
    freq = next((r for r in rows if r.logical_metric_key == "frequency_hz"), None)
    assert freq is not None
    assert abs(freq.value - 50.02) < 1e-3


@pytest.mark.asyncio
async def test_poll_block_records_modbus_error_on_exception(loaded_profile_and_catalog, tmp_path):
    profile, catalog, decoders = loaded_profile_and_catalog
    realtime = next(b for b in profile.read_blocks if b.name == "realtime")

    class FailingModbus:
        async def read_holding_registers(self, *a, **kw):
            raise ConnectionError("network down")

    buffer = Buffer(tmp_path / "b.db")
    await buffer.init()
    metrics = EdgeMetrics()
    await poll_block_once(
        client=FailingModbus(), profile=profile, catalog=catalog, decoders=decoders,
        block=realtime, device_id="dev-1", unit_id=1,
        buffer=buffer, metrics=metrics,
    )
    assert metrics.modbus_errors_per_minute_total() == 1.0
    assert await buffer.fetch_unpublished(limit=10) == []
```

- [ ] **Step 2: Implement**

```python
# packages/edge_agent/src/edge_agent/modbus/__init__.py
```

```python
# packages/edge_agent/src/edge_agent/modbus/client.py
"""ModbusClient Protocol — same shape used by the profile_loader fingerprint code.
We re-export to keep the edge-agent's import surface flat."""
from profile_loader.fingerprint import ModbusClient  # noqa: F401
```

```python
# packages/edge_agent/src/edge_agent/modbus/poller.py
"""Async Modbus poller — one task per read block.

Each call to poll_block_once does ONE FC03 read and decodes per profile. The
loop in __main__.py schedules these at block.cadence_s intervals.

On 10 consecutive failures, the loop halts the block (records in EdgeMetrics
so the heartbeat publishes halted_blocks).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog

from ..buffer.store import Buffer
from ..metrics import EdgeMetrics
from profile_loader import Catalog, Profile, ReadBlock

log = structlog.get_logger()

HALT_THRESHOLD = 10           # consecutive failures before halting a block


def _registers_to_bytes(registers: list[int]) -> bytes:
    out = bytearray()
    for r in registers:
        out.extend(int(r).to_bytes(2, "big", signed=False))
    return bytes(out)


async def poll_block_once(
    *, client, profile: Profile, catalog: Catalog, decoders: dict,
    block: ReadBlock, device_id: str, unit_id: int,
    buffer: Buffer, metrics: EdgeMetrics,
) -> bool:
    """Poll one block once. Returns True on success, False on failure."""
    try:
        if block.fc == 3:
            response = await client.read_holding_registers(block.address, block.length, slave=unit_id)
        elif block.fc == 4:
            response = await client.read_input_registers(block.address, block.length, slave=unit_id)
        else:
            raise ValueError(f"unsupported fc: {block.fc}")
        if bool(getattr(response, "isError", lambda: False)()):
            raise RuntimeError(f"modbus error: exception {getattr(response, 'exception_code', None)!r}")
        raw_bytes = _registers_to_bytes(getattr(response, "registers", []))
    except Exception as e:
        log.warning("modbus.read_failed", block=block.name, error=str(e))
        metrics.record_modbus_error()
        return False

    metrics.record_modbus_success()
    metrics.unhalt_block(block.name)

    readings = profile.decode(block.name, raw_bytes, catalog=catalog, decoders=decoders)
    now = datetime.now(timezone.utc)
    await buffer.insert_readings(
        block_name=block.name, time=now, device_id=device_id,
        readings=[(k, r.value if isinstance(r.value, (int, float)) else None, r.quality)
                  for k, r in readings.items()],
    )
    return True


async def poll_block_loop(
    *, client, profile: Profile, catalog: Catalog, decoders: dict,
    block: ReadBlock, device_id: str, unit_id: int,
    buffer: Buffer, metrics: EdgeMetrics,
) -> None:
    """Schedule one block forever at block.cadence_s; halt after threshold of consecutive failures."""
    consecutive_failures = 0
    while True:
        if block.name in metrics.halted_blocks:
            await asyncio.sleep(block.cadence_s)
            continue
        ok = await poll_block_once(
            client=client, profile=profile, catalog=catalog, decoders=decoders,
            block=block, device_id=device_id, unit_id=unit_id,
            buffer=buffer, metrics=metrics,
        )
        if ok:
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            if consecutive_failures >= HALT_THRESHOLD:
                log.error("modbus.block_halted", block=block.name, after=consecutive_failures)
                metrics.halt_block(block.name)
        await asyncio.sleep(block.cadence_s)
```

- [ ] **Step 3: Run + commit**

```bash
python -m pytest packages/edge_agent/tests/integration/test_modbus_poller.py -v
git add packages/edge_agent/src/edge_agent/modbus/ packages/edge_agent/tests/integration/test_modbus_poller.py
git commit -m "feat(edge-agent): Modbus poller with halt-on-consecutive-failures"
```

---

## Task 8: MQTT publisher (drains buffer → telemetry topic)

**Files:**
- Create: `packages/edge_agent/src/edge_agent/mqtt/__init__.py`
- Create: `packages/edge_agent/src/edge_agent/mqtt/client.py`
- Create: `packages/edge_agent/src/edge_agent/mqtt/publisher.py`
- Create: `packages/edge_agent/tests/unit/test_publish_payload_shape.py`
- Create: `packages/edge_agent/tests/integration/test_mqtt_publisher.py`

- [ ] **Step 1: Failing tests**

```python
# packages/edge_agent/tests/unit/test_publish_payload_shape.py
from datetime import datetime, timezone

from edge_agent.mqtt.publisher import build_telemetry_payload


def test_payload_shape_matches_mqtt_contract():
    """Spec: cloud/mqtt-contracts.md §4.1."""
    from edge_agent.buffer.store import BufferRow
    rows = [
        BufferRow(id=1, block_name="realtime", time=datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc),
                  device_id="dev-1", logical_metric_key="frequency_hz", value=50.02, quality="good"),
        BufferRow(id=2, block_name="realtime", time=datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc),
                  device_id="dev-1", logical_metric_key="active_power_total", value=12.35, quality="good"),
    ]
    payload = build_telemetry_payload(
        site_slug="bench", device_id="dev-1",
        block_name="realtime", time=rows[0].time, rows=rows, source="modbus_poll",
    )
    assert payload["version"] == "1.0"
    assert payload["site_slug"] == "bench"
    assert payload["device_id"] == "dev-1"
    assert payload["block"] == "realtime"
    assert payload["source"] == "modbus_poll"
    assert payload["timestamp"].endswith("Z")
    assert payload["readings"] == {"frequency_hz": 50.02, "active_power_total": 12.35}


def test_quality_is_worst_of_all_rows():
    """Quality field is the worst quality across all rows in the block."""
    from edge_agent.buffer.store import BufferRow
    rows = [
        BufferRow(id=1, block_name="r", time=datetime(2026, 1, 1, tzinfo=timezone.utc),
                  device_id="d", logical_metric_key="a", value=1.0, quality="good"),
        BufferRow(id=2, block_name="r", time=datetime(2026, 1, 1, tzinfo=timezone.utc),
                  device_id="d", logical_metric_key="b", value=2.0, quality="uncertain"),
    ]
    payload = build_telemetry_payload(site_slug="s", device_id="d", block_name="r",
                                       time=rows[0].time, rows=rows, source="modbus_poll")
    assert payload["quality"] == "uncertain"
```

```python
# packages/edge_agent/tests/integration/test_mqtt_publisher.py
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from edge_agent.buffer.store import Buffer
from edge_agent.mqtt.publisher import publish_pending_batch


class CapturingMqtt:
    def __init__(self):
        self.published: list[tuple[str, dict, int, bool]] = []

    async def publish(self, topic: str, payload, qos: int = 1, retain: bool = False):
        body = json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else payload)
        self.published.append((topic, body, qos, retain))


@pytest.mark.asyncio
async def test_publish_pending_batch_drains_buffer_and_marks_published(tmp_path: Path):
    buf = Buffer(tmp_path / "b.db")
    await buf.init()
    now = datetime.now(timezone.utc)
    await buf.insert_readings(block_name="realtime", time=now, device_id="dev-1",
                              readings=[("frequency_hz", 50.02, "good"),
                                        ("active_power_total", 12.35, "good")])
    mqtt = CapturingMqtt()
    await publish_pending_batch(mqtt=mqtt, buffer=buf, site_slug="bench", device_id="dev-1")
    assert len(mqtt.published) == 1
    topic, body, qos, retain = mqtt.published[0]
    assert topic == "solamon/bench/telemetry/dev-1"
    assert body["readings"]["frequency_hz"] == 50.02
    assert qos == 1
    assert retain is False
    # All rows marked published
    assert await buf.fetch_unpublished(limit=10) == []


@pytest.mark.asyncio
async def test_publish_groups_rows_by_block_and_time(tmp_path: Path):
    """Rows from different blocks become separate MQTT messages."""
    buf = Buffer(tmp_path / "b.db")
    await buf.init()
    t1 = datetime(2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 5, 3, 12, 1, 0, tzinfo=timezone.utc)
    await buf.insert_readings(block_name="realtime", time=t1, device_id="d",
                              readings=[("a", 1.0, "good")])
    await buf.insert_readings(block_name="energy", time=t2, device_id="d",
                              readings=[("b", 2.0, "good")])
    mqtt = CapturingMqtt()
    await publish_pending_batch(mqtt=mqtt, buffer=buf, site_slug="s", device_id="d")
    assert len(mqtt.published) == 2
    blocks = {body["block"] for _, body, _, _ in mqtt.published}
    assert blocks == {"realtime", "energy"}
```

- [ ] **Step 2: Implement `mqtt/client.py` + `mqtt/publisher.py`**

```python
# packages/edge_agent/src/edge_agent/mqtt/client.py
"""MqttClient Protocol — see SOLID-D in conventions."""
from __future__ import annotations

from typing import Any, Protocol


class MqttClient(Protocol):
    async def publish(self, topic: str, payload: bytes | str,
                      qos: int = 1, retain: bool = False) -> None: ...
```

```python
# packages/edge_agent/src/edge_agent/mqtt/publisher.py
"""Drain SQLite buffer → MQTT telemetry topic."""
from __future__ import annotations

import json
from datetime import datetime
from itertools import groupby

import structlog

from ..buffer.store import Buffer, BufferRow
from .client import MqttClient

log = structlog.get_logger()


def _quality_rank(q: str) -> int:
    return {"bad": 2, "uncertain": 1, "good": 0}.get(q, 0)


def _worst_quality(rows: list[BufferRow]) -> str:
    return max((r.quality for r in rows), key=_quality_rank)


def build_telemetry_payload(
    *, site_slug: str, device_id: str, block_name: str, time: datetime,
    rows: list[BufferRow], source: str,
) -> dict:
    return {
        "version": "1.0",
        "site_slug": site_slug,
        "device_id": device_id,
        "timestamp": time.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "block": block_name,
        "source": source,
        "quality": _worst_quality(rows),
        "readings": {r.logical_metric_key: r.value for r in rows},
    }


async def publish_pending_batch(
    *, mqtt: MqttClient, buffer: Buffer, site_slug: str, device_id: str,
    batch_limit: int = 200,
) -> int:
    """Fetch up to batch_limit rows; group by (block, time); publish + mark."""
    rows = await buffer.fetch_unpublished(limit=batch_limit)
    if not rows:
        return 0

    rows.sort(key=lambda r: (r.block_name, r.time))
    n_published = 0
    for (block_name, time), group_iter in groupby(rows, key=lambda r: (r.block_name, r.time)):
        group = list(group_iter)
        payload = build_telemetry_payload(
            site_slug=site_slug, device_id=device_id,
            block_name=block_name, time=time, rows=group,
            source="modbus_poll",        # could be 'replay_buffer' if rows are stale; left static for now
        )
        topic = f"solamon/{site_slug}/telemetry/{device_id}"
        await mqtt.publish(topic, json.dumps(payload).encode("utf-8"), qos=1, retain=False)
        await buffer.mark_published([r.id for r in group])
        n_published += len(group)
    return n_published
```

- [ ] **Step 3: Run + commit**

```bash
python -m pytest packages/edge_agent/tests/unit/test_publish_payload_shape.py packages/edge_agent/tests/integration/test_mqtt_publisher.py -v
git add packages/edge_agent/src/edge_agent/mqtt/ packages/edge_agent/tests/
git commit -m "feat(edge-agent): MQTT publisher (drains buffer; per-block per-time messages)"
```

---

## Task 9: Heartbeat publisher

**Files:**
- Create: `packages/edge_agent/src/edge_agent/mqtt/heartbeat.py`
- Tests: extend `test_mqtt_publisher.py`

- [ ] **Step 1: Failing test** (append to test_mqtt_publisher.py)

```python
import json

from edge_agent.metrics import EdgeMetrics
from edge_agent.mqtt.heartbeat import build_heartbeat_payload


def test_heartbeat_payload_includes_halted_blocks_and_metrics():
    metrics = EdgeMetrics()
    metrics.halt_block("energy")
    metrics.record_modbus_success()
    payload = build_heartbeat_payload(
        site_slug="bench", edge_version="0.1.0",
        buffer_depth_seconds=5, metrics=metrics,
    )
    assert payload["version"] == "1.0"
    assert payload["site_slug"] == "bench"
    assert payload["status"] == "online"
    assert payload["buffer_depth_seconds"] == 5
    assert "energy" in payload["halted_blocks"]
    assert payload["last_modbus_success"] is not None
    assert payload["timestamp"].endswith("Z")
```

- [ ] **Step 2: Implement**

```python
# packages/edge_agent/src/edge_agent/mqtt/heartbeat.py
"""Heartbeat publish — every 60s, retain=True, with LWT registered at connect."""
from __future__ import annotations

import asyncio
import json

import structlog

from ..buffer.store import Buffer
from ..metrics import EdgeMetrics
from ..now import now_utc
from .client import MqttClient

log = structlog.get_logger()


def build_heartbeat_payload(
    *, site_slug: str, edge_version: str,
    buffer_depth_seconds: int, metrics: EdgeMetrics,
) -> dict:
    return {
        "version": "1.0",
        "site_slug": site_slug,
        "timestamp": now_utc(),
        "status": "online",
        "edge_version": edge_version,
        "buffer_depth_seconds": buffer_depth_seconds,
        "last_modbus_success": metrics.last_modbus_success_iso(),
        "modbus_errors_per_minute": metrics.modbus_errors_per_minute_total(),
        "halted_blocks": sorted(metrics.halted_blocks),
    }


async def heartbeat_loop(
    *, mqtt: MqttClient, buffer: Buffer, metrics: EdgeMetrics,
    site_slug: str, edge_version: str, interval_s: float = 60.0,
) -> None:
    while True:
        try:
            depth = await buffer.compute_buffer_depth_seconds()
            payload = build_heartbeat_payload(
                site_slug=site_slug, edge_version=edge_version,
                buffer_depth_seconds=depth, metrics=metrics,
            )
            await mqtt.publish(
                f"solamon/{site_slug}/heartbeat",
                json.dumps(payload).encode("utf-8"),
                qos=1, retain=True,
            )
        except Exception as e:
            log.warning("heartbeat.failed", error=str(e))
        await asyncio.sleep(interval_s)
```

- [ ] **Step 3: Run + commit**

```bash
python -m pytest packages/edge_agent/tests/integration/test_mqtt_publisher.py -v
git add packages/edge_agent/src/edge_agent/mqtt/heartbeat.py packages/edge_agent/tests/integration/test_mqtt_publisher.py
git commit -m "feat(edge-agent): heartbeat publisher with halted_blocks + LWT-ready"
```

---

## Task 10: Command subscriber (write + readback + ack)

**Files:**
- Create: `packages/edge_agent/src/edge_agent/mqtt/command_subscriber.py`
- Create: `packages/edge_agent/tests/unit/test_command_validation.py`
- Create: `packages/edge_agent/tests/integration/test_command_subscriber_round_trip.py`

- [ ] **Step 1: Failing tests**

```python
# packages/edge_agent/tests/unit/test_command_validation.py
from pathlib import Path

import pytest
from profile_loader import ProfileLoader, ValidationError


REPO_ROOT = Path(__file__).resolve().parents[5]


def test_validate_control_through_profile_loader():
    """Edge agent uses profile_loader.Profile.validate_control directly —
    SOLID-D: no second copy of validation logic in the edge agent."""
    loader = ProfileLoader()
    catalog = loader.load_catalog(REPO_ROOT / "architecture" / "logical_metrics.yaml")
    profile = loader.load_profile(REPO_ROOT / "architecture" / "profiles" / "acuvim_l.yaml", catalog)
    # demand_window_minutes is writable + allowed_values [1,5,10,15,30]
    profile.validate_control("demand_window_minutes", 30, catalog=catalog)
    with pytest.raises(ValidationError):
        profile.validate_control("demand_window_minutes", 99, catalog=catalog)
```

```python
# packages/edge_agent/tests/integration/test_command_subscriber_round_trip.py
"""Test the command-handling pipeline: incoming command → write → readback → ack."""
import json
import struct
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from edge_agent.mqtt.command_subscriber import handle_command
from profile_loader import ProfileLoader

REPO_ROOT = Path(__file__).resolve().parents[5]


class FakeWriteResponse:
    def isError(self): return False


class FakeReadResponse:
    def __init__(self, registers: list[int]):
        self.registers = registers
    def isError(self): return False


class FakeModbus:
    def __init__(self):
        self.writes: list[tuple[int, int]] = []
        self.read_value = 30

    async def write_register(self, address: int, value: int, slave: int = 1):
        self.writes.append((address, value))
        return FakeWriteResponse()

    async def read_holding_registers(self, address: int, count: int, slave: int = 1):
        # Return the value we 'wrote' so readback succeeds
        return FakeReadResponse([self.read_value])


class CapturingMqtt:
    def __init__(self):
        self.published: list[tuple[str, dict]] = []

    async def publish(self, topic: str, payload, qos: int = 1, retain: bool = False):
        body = json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else payload)
        self.published.append((topic, body))


@pytest.fixture
def loaded_acuvim_l():
    loader = ProfileLoader()
    catalog = loader.load_catalog(REPO_ROOT / "architecture" / "logical_metrics.yaml")
    profile = loader.load_profile(REPO_ROOT / "architecture" / "profiles" / "acuvim_l.yaml", catalog)
    return catalog, profile


@pytest.mark.asyncio
async def test_command_writes_then_readback_then_publishes_confirmed_ack(
    loaded_acuvim_l,
):
    catalog, profile = loaded_acuvim_l
    cmd_id = str(uuid4())
    incoming = {
        "version": "1.0",
        "id": cmd_id,
        "site_slug": "bench",
        "device_id": "dev-1",
        "logical_metric": "demand_window_minutes",
        "type": "set_value",
        "parameters": {"value": 30},
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "issued_by": "00000000-0000-0000-0000-000000000001",
        "expires_at": "2099-01-01T00:00:00Z",
    }
    modbus = FakeModbus()
    modbus.read_value = 30
    mqtt = CapturingMqtt()
    await handle_command(
        client=modbus, mqtt=mqtt, profile=profile, catalog=catalog,
        site_slug="bench", device_id="dev-1", unit_id=1,
        command=incoming, readback_delay_override_s=0.0,
    )
    assert len(modbus.writes) == 1
    assert len(mqtt.published) == 1
    topic, body = mqtt.published[0]
    assert topic == "solamon/bench/commands/dev-1/ack"
    assert body["status"] == "confirmed"
    assert body["confirmed_value"] == {"value": 30}


@pytest.mark.asyncio
async def test_command_rejects_invalid_value_with_failed_ack(loaded_acuvim_l):
    catalog, profile = loaded_acuvim_l
    incoming = {
        "version": "1.0",
        "id": str(uuid4()),
        "site_slug": "bench", "device_id": "dev-1",
        "logical_metric": "demand_window_minutes", "type": "set_value",
        "parameters": {"value": 99},        # not in allowed_values
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "issued_by": "00000000-0000-0000-0000-000000000001",
        "expires_at": "2099-01-01T00:00:00Z",
    }
    modbus = FakeModbus()
    mqtt = CapturingMqtt()
    await handle_command(
        client=modbus, mqtt=mqtt, profile=profile, catalog=catalog,
        site_slug="bench", device_id="dev-1", unit_id=1,
        command=incoming, readback_delay_override_s=0.0,
    )
    # No write attempted
    assert modbus.writes == []
    # Failed ack published
    assert len(mqtt.published) == 1
    _, body = mqtt.published[0]
    assert body["status"] == "failed"
    assert "allowed" in body["error_message"].lower()


@pytest.mark.asyncio
async def test_command_readback_mismatch_publishes_failed_ack(loaded_acuvim_l):
    catalog, profile = loaded_acuvim_l
    cmd = {
        "version": "1.0", "id": str(uuid4()),
        "site_slug": "bench", "device_id": "dev-1",
        "logical_metric": "demand_window_minutes", "type": "set_value",
        "parameters": {"value": 30},
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "issued_by": "00000000-0000-0000-0000-000000000001",
        "expires_at": "2099-01-01T00:00:00Z",
    }
    modbus = FakeModbus()
    modbus.read_value = 15            # readback returns 15, not 30
    mqtt = CapturingMqtt()
    await handle_command(
        client=modbus, mqtt=mqtt, profile=profile, catalog=catalog,
        site_slug="bench", device_id="dev-1", unit_id=1,
        command=cmd, readback_delay_override_s=0.0,
    )
    _, body = mqtt.published[0]
    assert body["status"] == "failed"
    assert "readback" in body["error_message"].lower()
```

- [ ] **Step 2: Implement**

```python
# packages/edge_agent/src/edge_agent/mqtt/command_subscriber.py
"""Command handler: parse → validate → write → readback → ack.

Spec: cloud/control-relay.md §2-3 + edge-agent/command-subscriber.md.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from profile_loader import Catalog, Profile, ValidationError
from profile_loader.fingerprint import _registers_to_bytes
from profile_loader.decoders import decode_format

from ..now import now_utc
from .client import MqttClient

log = structlog.get_logger()


async def handle_command(
    *, client, mqtt: MqttClient, profile: Profile, catalog: Catalog,
    site_slug: str, device_id: str, unit_id: int,
    command: dict[str, Any], readback_delay_override_s: float | None = None,
) -> None:
    """Process one incoming command. Always publishes an ack."""
    cmd_id = command["id"]
    logical = command["logical_metric"]
    value = command["parameters"]["value"]
    received_at = now_utc()

    # 1. Validate.
    try:
        profile.validate_control(logical, value, catalog=catalog)
    except ValidationError as e:
        await _publish_ack(mqtt, site_slug, device_id, cmd_id, "failed",
                           received_at=received_at, error=str(e))
        return

    spec = profile.control[logical]

    # 2. Write.
    try:
        if spec.fc == 6:
            response = await client.write_register(spec.address, int(value), slave=unit_id)
        else:                                        # fc 16 — write multiple
            response = await client.write_registers(spec.address, [int(value)], slave=unit_id)
        if bool(getattr(response, "isError", lambda: False)()):
            raise RuntimeError("modbus write returned error")
        write_at = now_utc()
    except Exception as e:
        await _publish_ack(mqtt, site_slug, device_id, cmd_id, "failed",
                           received_at=received_at, error=f"write failed: {e}")
        return

    # 3. Readback.
    delay_s = (readback_delay_override_s
               if readback_delay_override_s is not None
               else spec.readback_delay_ms / 1000.0)
    await asyncio.sleep(delay_s)

    rb = spec.readback_register
    rb_address = rb.address if rb else spec.address
    rb_format = rb.format if rb else spec.format
    rb_offset = rb.offset if rb else 0
    rb_fc = rb.fc if rb else 3

    try:
        if rb_fc == 3:
            rb_response = await client.read_holding_registers(rb_address, 1, slave=unit_id)
        else:
            rb_response = await client.read_input_registers(rb_address, 1, slave=unit_id)
        rb_bytes = _registers_to_bytes(getattr(rb_response, "registers", []))
        actual = decode_format(rb_format, rb_bytes, rb_offset)
    except Exception as e:
        await _publish_ack(mqtt, site_slug, device_id, cmd_id, "failed",
                           received_at=received_at, write_at=write_at,
                           error=f"readback failed: {e}")
        return

    # 4. Compare.
    if not _values_match(rb_format, actual, value):
        await _publish_ack(mqtt, site_slug, device_id, cmd_id, "failed",
                           received_at=received_at, write_at=write_at,
                           error=f"readback mismatch: wrote {value!r}, read {actual!r}")
        return

    await _publish_ack(mqtt, site_slug, device_id, cmd_id, "confirmed",
                       received_at=received_at, write_at=write_at,
                       confirmed_value={"value": value})


def _values_match(format: str, actual: Any, expected: Any) -> bool:
    if format.startswith("float"):
        try:
            return abs(float(actual) - float(expected)) <= max(1e-6, 1e-6 * abs(float(expected)))
        except (TypeError, ValueError):
            return False
    return actual == expected


async def _publish_ack(
    mqtt: MqttClient, site_slug: str, device_id: str, cmd_id: str, status: str,
    *, received_at: str, write_at: str | None = None,
    confirmed_value: dict | None = None, error: str | None = None,
) -> None:
    payload = {
        "version": "1.0", "id": cmd_id,
        "site_slug": site_slug, "device_id": device_id,
        "status": status, "received_at": received_at,
        "modbus_write_at": write_at,
        "confirmed_value": confirmed_value, "error_message": error,
    }
    topic = f"solamon/{site_slug}/commands/{device_id}/ack"
    await mqtt.publish(topic, json.dumps(payload).encode("utf-8"), qos=1)
    log.info("command.ack_published", id=cmd_id, status=status)
```

- [ ] **Step 3: Run + commit**

```bash
python -m pytest packages/edge_agent/tests/integration/test_command_subscriber_round_trip.py packages/edge_agent/tests/unit/test_command_validation.py -v
git add packages/edge_agent/src/edge_agent/mqtt/command_subscriber.py packages/edge_agent/tests/
git commit -m "feat(edge-agent): command subscriber with validate + write + readback + ack"
```

---

## Task 11: Composition root + Dockerfile

**Files:**
- Create: `packages/edge_agent/src/edge_agent/__main__.py`
- Create: `packages/edge_agent/Dockerfile`

- [ ] **Step 1: Implement composition root**

```python
# packages/edge_agent/src/edge_agent/__main__.py
"""Composition root for the edge agent.

Wires concrete adapters (pymodbus AsyncModbusTcpClient, asyncio_mqtt.Client,
aiosqlite-backed Buffer) into the Protocol-typed layers.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import structlog
from asyncio_mqtt import Client as MqttBrokerClient, Will
from pymodbus.client import AsyncModbusTcpClient

from . import __version__
from .buffer.rotation import rotation_loop
from .buffer.store import Buffer
from .config.bootstrap import load_bootstrap
from .config.site_config import fetch_site_config, load_cached_site_config
from .metrics import EdgeMetrics
from .modbus.poller import poll_block_loop
from .mqtt.command_subscriber import handle_command
from .mqtt.heartbeat import heartbeat_loop
from .mqtt.publisher import publish_pending_batch
from .now import now_utc
from profile_loader import ProfileLoader

log = structlog.get_logger()

CONFIG_PATH = Path(os.environ.get("SOLAMON_CONFIG", "/etc/solamon/bootstrap.yaml"))
SITE_CACHE = Path("/var/lib/solamon/site_config.json")
BUFFER_PATH = Path("/var/lib/solamon/buffer.db")


async def amain() -> None:
    bs = load_bootstrap(CONFIG_PATH)
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(getattr(__import__("logging"), bs.log_level))
    )

    # 1. Fetch (or load cached) site config.
    try:
        site = fetch_site_config(
            cloud_url=bs.cloud_url, site_slug=bs.site_slug,
            bearer_token=bs.bearer_token, cache_path=SITE_CACHE,
        )
    except Exception as e:
        log.warning("site_config.fetch_failed", error=str(e))
        site = load_cached_site_config(SITE_CACHE)

    # 2. Load profile + catalog (in-process).
    loader = ProfileLoader()
    catalog_path = Path("/tmp/catalog.yaml")
    catalog_path.write_text(__import__("yaml").safe_dump(site.catalog), encoding="utf-8")
    profile_path = Path("/tmp/profile.yaml")
    profile_path.write_text(__import__("yaml").safe_dump(site.profile), encoding="utf-8")
    catalog = loader.load_catalog(catalog_path)
    profile = loader.load_profile(profile_path, catalog)

    # 3. Buffer.
    buffer = Buffer(BUFFER_PATH)
    await buffer.init()
    metrics = EdgeMetrics()

    # 4. Modbus client.
    modbus = AsyncModbusTcpClient(host=site.device_host, port=site.device_port)
    await modbus.connect()

    # 5. MQTT — connect with LWT.
    lwt_topic = f"solamon/{site.site_slug}/heartbeat"
    lwt_payload = json.dumps({
        "version": "1.0", "site_slug": site.site_slug,
        "timestamp": now_utc(), "status": "offline",
    }).encode("utf-8")

    async with MqttBrokerClient(
        hostname=site.mqtt.broker_host, port=site.mqtt.broker_port,
        username=site.mqtt.username, password=site.mqtt.password,
        client_id=site.mqtt.client_id, keepalive=60,
        will=Will(topic=lwt_topic, payload=lwt_payload, qos=1, retain=True),
    ) as mqtt:
        # Subscribe to commands for our device.
        cmd_topic = f"solamon/{site.site_slug}/commands/{site.device_id}"
        await mqtt.subscribe(cmd_topic, qos=1)

        # Schedule poller per block.
        poll_tasks = [
            asyncio.create_task(poll_block_loop(
                client=modbus, profile=profile, catalog=catalog,
                decoders=loader.decoders, block=block,
                device_id=site.device_id, unit_id=site.device_unit_id,
                buffer=buffer, metrics=metrics,
            ))
            for block in profile.read_blocks
        ]

        async def publish_loop():
            while True:
                try:
                    await publish_pending_batch(
                        mqtt=mqtt, buffer=buffer,
                        site_slug=site.site_slug, device_id=site.device_id,
                    )
                except Exception as e:
                    log.error("publisher.failed", error=str(e))
                await asyncio.sleep(0.5)

        async def command_loop():
            async with mqtt.messages() as messages:
                async for msg in messages:
                    if str(msg.topic) != cmd_topic:
                        continue
                    try:
                        cmd = json.loads(msg.payload.decode("utf-8"))
                        await handle_command(
                            client=modbus, mqtt=mqtt, profile=profile, catalog=catalog,
                            site_slug=site.site_slug, device_id=site.device_id,
                            unit_id=site.device_unit_id, command=cmd,
                        )
                    except Exception as e:
                        log.error("command.handle_failed", error=str(e))

        try:
            await asyncio.gather(
                *poll_tasks,
                publish_loop(),
                command_loop(),
                heartbeat_loop(mqtt=mqtt, buffer=buffer, metrics=metrics,
                               site_slug=site.site_slug, edge_version=__version__),
                rotation_loop(buffer),
            )
        finally:
            await modbus.close()


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Dockerfile**

```dockerfile
# packages/edge_agent/Dockerfile
FROM python:3.12-slim-bookworm AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends gcc python3-dev && rm -rf /var/lib/apt/lists/*

COPY packages/profile_loader /build/profile_loader
COPY packages/edge_agent     /build/edge_agent
RUN pip wheel --no-deps -w /wheels /build/profile_loader /build/edge_agent

FROM python:3.12-slim-bookworm
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl

ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "edge_agent"]
```

- [ ] **Step 3: Build + commit**

```bash
docker build -f packages/edge_agent/Dockerfile -t solamon-edge-agent:dev .
git add packages/edge_agent/src/edge_agent/__main__.py packages/edge_agent/Dockerfile
git commit -m "feat(edge-agent): composition root + ARM64 Dockerfile"
```

---

## Task 12: GitHub Actions CI

**Files:**
- Create: `.github/workflows/edge-agent.yml`

```yaml
name: Edge agent

on:
  push:
    branches: [master]
    paths:
      - "packages/edge_agent/**"
      - "packages/profile_loader/**"
      - "architecture/**"
      - ".github/workflows/edge-agent.yml"
  pull_request:
    paths:
      - "packages/edge_agent/**"
      - "packages/profile_loader/**"
      - "architecture/**"

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12", cache: "pip" }
      - run: |
          python -m pip install -e packages/profile_loader
          python -m pip install -e "packages/edge_agent[dev]"
      - run: python -m ruff check packages/edge_agent
      - run: python -m pytest packages/edge_agent/tests -v

  build-image:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - run: docker buildx build --platform linux/arm64 -f packages/edge_agent/Dockerfile -t solamon-edge-agent:ci .
```

- [ ] **Commit:**

```bash
python -m ruff check packages/edge_agent
git add .github/workflows/edge-agent.yml
git commit -m "ci(edge-agent): pytest + ruff + ARM64 image build"
```

---

## Self-review

| Spec | Task |
|------|------|
| Bootstrap config loader | Task 2 |
| Site config fetch + cache | Task 3 |
| SQLite buffer with idempotent insert | Task 4 |
| Buffer rotation | Task 5 |
| Modbus poller using profile_loader.decode | Task 7 |
| Halt-block on consecutive failures | Task 7 |
| MQTT publisher (per-block telemetry messages) | Task 8 |
| Heartbeat with halted_blocks + LWT | Task 9 |
| Command subscriber: validate → write → readback → ack | Task 10 |
| Composition root + Dockerfile | Task 11 |
| now_utc helper | Task 1 |

**Type consistency**: `BufferRow`, `BootstrapConfig`, `SiteConfig`, `MqttSettings`, `EdgeMetrics` defined and used consistently. The `ModbusClient` Protocol is imported from `profile_loader.fingerprint` rather than redeclared (SOLID-D: single Protocol, multiple consumers).

---

## Acceptance verification

```bash
python -m ruff check packages/edge_agent
python -m pytest packages/edge_agent -v
docker buildx build --platform linux/arm64 -f packages/edge_agent/Dockerfile -t solamon-edge-agent:test .
```

---

## Out of scope

Per [`2026-05-03-conventions.md` §7](2026-05-03-conventions.md): hot reload (SOL-17), profile auto-detection (SOL-11), AXM-WEB2 push (SOL-22), per-site profile overrides (SOL-13), profile editor UI (SOL-12).
