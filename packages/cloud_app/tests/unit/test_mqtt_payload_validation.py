import pytest
from pydantic import ValidationError

from cloud_app.mqtt.payloads import HeartbeatPayload, TelemetryPayload


def test_telemetry_payload_round_trips_valid_json():
    raw = {
        "version": "1.0",
        "site_slug": "bench",
        "device_id": "01952b7c-3a14-7000-8000-000000000001",
        "timestamp": "2026-05-03T12:00:00.000Z",
        "block": "realtime",
        "source": "modbus_poll",
        "quality": "good",
        "readings": {"frequency_hz": 50.02, "active_power_total": 12.35},
    }
    p = TelemetryPayload.model_validate(raw)
    assert p.readings["frequency_hz"] == 50.02


def test_telemetry_payload_rejects_unknown_source():
    with pytest.raises(ValidationError):
        TelemetryPayload.model_validate({
            "version": "1.0", "site_slug": "bench",
            "device_id": "01952b7c-3a14-7000-8000-000000000001",
            "timestamp": "2026-05-03T12:00:00.000Z",
            "block": "x", "source": "weird", "quality": "good", "readings": {},
        })


def test_heartbeat_payload_with_halted_blocks():
    p = HeartbeatPayload.model_validate({
        "version": "1.0", "site_slug": "bench",
        "timestamp": "2026-05-03T12:00:00.000Z",
        "status": "online", "edge_version": "0.1.0", "buffer_depth_seconds": 0,
        "last_modbus_success": "2026-05-03T11:59:55Z",
        "modbus_errors_per_minute": 0, "halted_blocks": ["energy"],
    })
    assert p.halted_blocks == ["energy"]


def test_heartbeat_payload_offline_minimal_shape():
    """LWT payload omits most fields."""
    p = HeartbeatPayload.model_validate({
        "version": "1.0", "site_slug": "bench",
        "timestamp": "2026-05-03T12:00:00.000Z", "status": "offline",
    })
    assert p.status == "offline"
