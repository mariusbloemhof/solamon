"""POC payload builders.

The cloud app currently ingests AXM-WEB2 native JSON from
solamon/{site}/acuvim/{device}/data, so the bench MVP publishes that shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sin

from . import __version__
from .config import BootstrapConfig
from .now import now_utc


@dataclass(frozen=True)
class EdgeSample:
    sequence: int
    timestamp: str


def build_heartbeat(config: BootstrapConfig, sample: EdgeSample) -> dict[str, object]:
    return {
        "version": "1.0",
        "site_slug": config.site_slug,
        "timestamp": sample.timestamp,
        "status": "online",
        "edge_version": __version__,
        "buffer_depth_seconds": 0,
        "last_modbus_success": sample.timestamp,
        "modbus_errors_per_minute": 0.0,
        "halted_blocks": [],
    }


def build_lwt(config: BootstrapConfig) -> dict[str, object]:
    return {
        "version": "1.0",
        "site_slug": config.site_slug,
        "timestamp": now_utc(),
        "status": "offline",
    }


def build_acuvim_native_payload(config: BootstrapConfig, sample: EdgeSample) -> dict[str, object]:
    phase = sin(sample.sequence / 3)
    active_power_w = 286_000 + (phase * 18_000)
    return {
        "timestamp": sample.timestamp,
        "gateway": {
            "name": "solamon-pi",
            "model": "Raspberry Pi 5",
            "serial": config.site_slug,
        },
        "device": {
            "name": f"Acuvim-{config.site_slug}",
            "model": "Acuvim L",
            "host": config.device_host,
            "unit_id": config.device_unit_id,
        },
        "readings": [
            {"param": "V1", "value": f"{230.8 + phase:.2f}", "unit": "V"},
            {"param": "V2", "value": f"{230.1 - phase * 0.4:.2f}", "unit": "V"},
            {"param": "V3", "value": f"{231.9 + phase * 0.3:.2f}", "unit": "V"},
            {"param": "I1", "value": f"{425.7 + phase * 12:.2f}", "unit": "A"},
            {"param": "I2", "value": f"{397.8 + phase * 10:.2f}", "unit": "A"},
            {"param": "I3", "value": f"{425.4 + phase * 9:.2f}", "unit": "A"},
            {"param": "Psum", "value": f"{active_power_w:.2f}", "unit": "W"},
            {"param": "Qsum", "value": f"{active_power_w * 0.34:.2f}", "unit": "var"},
            {"param": "Ssum", "value": f"{active_power_w / 0.94:.2f}", "unit": "VA"},
            {"param": "PF", "value": f"{0.94 + phase * 0.01:.3f}", "unit": ""},
            {"param": "Freq_Hz", "value": f"{50.02 + phase * 0.02:.3f}", "unit": "Hz"},
            {"param": "Ep_imp", "value": f"{1842.7 + sample.sequence * 0.12:.3f}", "unit": "kWh"},
            {"param": "Ep_exp", "value": f"{312.8 + sample.sequence * 0.02:.3f}", "unit": "kWh"},
        ],
    }
