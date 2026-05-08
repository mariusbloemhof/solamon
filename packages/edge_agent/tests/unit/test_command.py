import json
from datetime import UTC, datetime, timedelta
from typing import ClassVar

import pytest
from cachetools import TTLCache

from edge_agent.command import CommandPayload, handle_command
from edge_agent.config import BootstrapConfig
from edge_agent.site_config import fallback_site_config
from profile_loader.loader import ProfileLoader


class Result:
    registers: ClassVar[list[int]] = [30]
    exception_code = 0

    def isError(self):
        return False


class FakeModbus:
    def __init__(self):
        self.writes = 0

    async def write_register(self, address, value, slave):
        self.writes += 1
        return Result()

    async def read_holding_registers(self, address, count, slave):
        return Result()


class FakeMqtt:
    def __init__(self):
        self.published = []

    async def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, json.loads(payload), qos, retain))


def _setup():
    loader = ProfileLoader()
    catalog = loader.load_catalog("architecture/logical_metrics.yaml")
    profile = loader.load_profile("architecture/profiles/acuvim_l.yaml", catalog)
    config = fallback_site_config(
        BootstrapConfig("1.0", "bench", "https://cloud.amendi.dev", "secret", "192.168.1.254", 1)
    )
    return profile, catalog, config


def _command(value=30, expires_delta=timedelta(minutes=5)):
    expires = (datetime.now(UTC) + expires_delta).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    payload = {
        "id": "00000000-0000-4000-8000-000000000042",
        "site_slug": "bench",
        "device_id": "00000000-0000-4000-8000-000000000001",
        "logical_metric": "demand_window_minutes",
        "type": "set_value",
        "parameters": {"value": value},
        "issued_at": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "issued_by": "00000000-0000-4000-8000-000000000099",
        "expires_at": expires,
    }
    return CommandPayload.from_json(json.dumps(payload))


@pytest.mark.asyncio
async def test_command_confirmed_and_deduplicated():
    profile, catalog, config = _setup()
    mqtt = FakeMqtt()
    modbus = FakeModbus()
    recent = TTLCache(maxsize=1000, ttl=300)

    ack = await handle_command(
        client=mqtt,
        site_config=config,
        profile=profile,
        catalog=catalog,
        modbus=modbus,
        command=_command(),
        recent=recent,
    )
    duplicate = await handle_command(
        client=mqtt,
        site_config=config,
        profile=profile,
        catalog=catalog,
        modbus=modbus,
        command=_command(),
        recent=recent,
    )

    assert ack["status"] == "confirmed"
    assert duplicate == ack
    assert modbus.writes == 1


@pytest.mark.asyncio
async def test_command_rejects_disallowed_value():
    profile, catalog, config = _setup()
    ack = await handle_command(
        client=FakeMqtt(),
        site_config=config,
        profile=profile,
        catalog=catalog,
        modbus=FakeModbus(),
        command=_command(value=42),
        recent=TTLCache(maxsize=1000, ttl=300),
    )

    assert ack["status"] == "failed"
    assert "allowed" in ack["error_message"]
