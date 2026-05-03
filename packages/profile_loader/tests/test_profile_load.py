from pathlib import Path

import yaml

from profile_loader.profile import (
    ConnectionInfo, DeviceInfo, MetricMap, Profile, ReadBlock,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
ACUVIM_L_PATH = REPO_ROOT / "architecture" / "profiles" / "acuvim_l.yaml"


def _acuvim_l_dict() -> dict:
    with ACUVIM_L_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_profile_from_dict_parses_device_info():
    profile = Profile.from_dict(_acuvim_l_dict())
    assert isinstance(profile.device, DeviceInfo)
    assert profile.device.manufacturer == "AccuEnergy"
    assert profile.device.model == "Acuvim L"
    assert profile.device.category == "meter"


def test_profile_from_dict_parses_connection():
    profile = Profile.from_dict(_acuvim_l_dict())
    assert isinstance(profile.connection, ConnectionInfo)
    assert profile.connection.protocol == "modbus_tcp"
    assert profile.connection.default_port == 502


def test_profile_from_dict_parses_read_blocks():
    profile = Profile.from_dict(_acuvim_l_dict())
    realtime = next((b for b in profile.read_blocks if b.name == "realtime"), None)
    assert realtime is not None
    assert isinstance(realtime, ReadBlock)
    assert realtime.fc == 3
    assert realtime.cadence_s > 0
    assert realtime.length > 0
    assert all(isinstance(m, MetricMap) for m in realtime.metrics)


def test_profile_schedule_yields_blocks():
    profile = Profile.from_dict(_acuvim_l_dict())
    scheduled = list(profile.schedule())
    assert len(scheduled) == len(profile.read_blocks)
    for block, cadence in scheduled:
        assert isinstance(block, ReadBlock)
        assert cadence == block.cadence_s
