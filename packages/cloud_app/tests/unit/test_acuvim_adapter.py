"""AXM-WEB2 native payload → TelemetryPayload."""
from uuid import uuid4

import pytest

from cloud_app.mqtt.adapters.acuvim import parse_acuvim_payload


SAMPLE = {
    "timestamp": "2026-05-09T10:30:00Z",
    "gateway": {"name": "AXM-WEB2", "model": "AXM-WEB2", "serial": "AND00123456"},
    "device":  {"name": "Bench-Acuvim", "model": "Acuvim-L"},
    "readings": [
        {"param": "V1",       "value": "230.5",   "unit": "V"},
        {"param": "V2",       "value": "231.2",   "unit": "V"},
        {"param": "V3",       "value": "230.8",   "unit": "V"},
        {"param": "I1",       "value": "15.3",    "unit": "A"},
        {"param": "I2",       "value": "14.9",    "unit": "A"},
        {"param": "I3",       "value": "15.1",    "unit": "A"},
        {"param": "Psum",     "value": "10530",   "unit": "W"},
        {"param": "Qsum",     "value": "1250",    "unit": "var"},
        {"param": "Ssum",     "value": "10604",   "unit": "VA"},
        {"param": "PF",       "value": "0.993",   "unit": ""},
        {"param": "Freq_Hz",  "value": "50.01",   "unit": "Hz"},
        {"param": "Ep_imp",   "value": "12530.5", "unit": "kWh"},
        {"param": "Ep_exp",   "value": "0.0",     "unit": "kWh"},
        {"param": "LoadType", "value": "L",       "unit": ""},
    ],
}


def test_adapter_maps_param_names_to_logical_metric_keys():
    device_id = uuid4()
    p = parse_acuvim_payload(SAMPLE, site_slug="bench", device_id=device_id)
    assert p.site_slug == "bench"
    assert p.device_id == device_id
    assert p.block == "realtime"
    assert p.source == "modbus_poll"
    assert p.quality == "good"
    assert "voltage_l1_n" in p.readings
    assert "frequency_hz" in p.readings
    assert "active_power_total" in p.readings


def test_adapter_converts_power_from_w_to_kw():
    p = parse_acuvim_payload(SAMPLE, site_slug="bench", device_id=uuid4())
    # Psum was 10530 W → 10.53 kW
    assert p.readings["active_power_total"] == pytest.approx(10.530)
    assert p.readings["reactive_power_total"] == pytest.approx(1.250)
    assert p.readings["apparent_power_total"] == pytest.approx(10.604)


def test_adapter_passes_through_voltage_current_freq_unchanged():
    p = parse_acuvim_payload(SAMPLE, site_slug="bench", device_id=uuid4())
    assert p.readings["voltage_l1_n"] == pytest.approx(230.5)
    assert p.readings["current_l3"] == pytest.approx(15.1)
    assert p.readings["frequency_hz"] == pytest.approx(50.01)
    assert p.readings["power_factor_total"] == pytest.approx(0.993)


def test_adapter_skips_non_numeric_params():
    """LoadType is an enum string ('L') — must not appear in readings dict."""
    p = parse_acuvim_payload(SAMPLE, site_slug="bench", device_id=uuid4())
    assert all(isinstance(v, float) for v in p.readings.values())
    # No mapping for LoadType → not in readings
    for unmapped in ("load_type", "LoadType"):
        assert unmapped not in p.readings


def test_adapter_skips_unknown_params_silently():
    """Future Acuvim firmware may add new params; ignore them, don't crash."""
    payload = {
        "timestamp": "2026-05-09T10:30:00Z",
        "readings": [
            {"param": "V1",       "value": "230",  "unit": "V"},
            {"param": "Mystery1", "value": "42",   "unit": "?"},
            {"param": "Mystery2", "value": "abc",  "unit": "?"},
        ],
    }
    p = parse_acuvim_payload(payload, site_slug="bench", device_id=uuid4())
    assert p.readings == {"voltage_l1_n": 230.0}


def test_adapter_skips_unparseable_values():
    """If a numeric param arrives as a non-numeric string, skip rather than fail."""
    payload = {
        "timestamp": "2026-05-09T10:30:00Z",
        "readings": [
            {"param": "V1", "value": "230.5", "unit": "V"},
            {"param": "V2", "value": "----",  "unit": "V"},
        ],
    }
    p = parse_acuvim_payload(payload, site_slug="bench", device_id=uuid4())
    assert p.readings == {"voltage_l1_n": 230.5}


# ─── Shape B (Johan's bench firmware): readings nested under `device`,
# unit-suffixed param names, unix-epoch timestamp.

JOHAN_FIRMWARE_SAMPLE = {
    "timestamp": 1778252253,
    "gateway": {"name": "AXM-WEB2", "model": "AXM-WEB2", "serial": "AN55101017"},
    "device": {
        "name": "",
        "model": "Acuvim-L",
        "serial": "CLD56020398",
        "online": True,
        "readings": [
            {"param": "V1",         "value": "230.4",  "unit": "V"},
            {"param": "V12",        "value": "399.1",  "unit": "V"},
            {"param": "I1",         "value": "10.2",   "unit": "A"},
            {"param": "In",         "value": "0.1",    "unit": "A"},
            {"param": "P1",         "value": "2.35",   "unit": "kW"},
            {"param": "Psum_kW",    "value": "7.05",   "unit": "kW"},
            {"param": "Qsum_kvar",  "value": "0.42",   "unit": "kvar"},
            {"param": "Ssum_kVA",   "value": "7.07",   "unit": "kVA"},
            {"param": "PF",         "value": "0.997",  "unit": ""},
            {"param": "Freq_Hz",    "value": "50.02",  "unit": "Hz"},
        ],
    },
}


def test_adapter_handles_nested_readings_under_device():
    p = parse_acuvim_payload(JOHAN_FIRMWARE_SAMPLE, site_slug="bench", device_id=uuid4())
    assert "voltage_l1_n" in p.readings
    assert "active_power_total" in p.readings
    assert "frequency_hz" in p.readings


def test_adapter_handles_unit_suffixed_param_names_without_double_scaling():
    """Psum_kW value 7.05 must land as 7.05 kW, not 0.00705 (no W→kW scale)."""
    p = parse_acuvim_payload(JOHAN_FIRMWARE_SAMPLE, site_slug="bench", device_id=uuid4())
    assert p.readings["active_power_total"] == pytest.approx(7.05)
    assert p.readings["reactive_power_total"] == pytest.approx(0.42)
    assert p.readings["apparent_power_total"] == pytest.approx(7.07)


def test_adapter_handles_unix_epoch_timestamp():
    p = parse_acuvim_payload(JOHAN_FIRMWARE_SAMPLE, site_slug="bench", device_id=uuid4())
    # Pydantic v2 coerces unix-epoch int → tz-aware datetime.
    assert p.timestamp.year == 2026


def test_adapter_maps_line_line_voltage_and_neutral_current():
    p = parse_acuvim_payload(JOHAN_FIRMWARE_SAMPLE, site_slug="bench", device_id=uuid4())
    assert p.readings["voltage_l1_l2"] == pytest.approx(399.1)
    assert p.readings["current_neutral"] == pytest.approx(0.1)
    assert p.readings["active_power_l1"] == pytest.approx(2.35)
