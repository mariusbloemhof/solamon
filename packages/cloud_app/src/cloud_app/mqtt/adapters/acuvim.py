"""AXM-WEB2 native payload → TelemetryPayload adapter.

The Acuvim L AXM-WEB2 publishes JSON with a fixed shape (see
discovery/specs/acuvim_l_axm_web2_configuration.md §2.6):

    {
      "timestamp": "2025-09-15T10:30:00Z",
      "gateway": {"name", "model", "serial"},
      "device":  {"name", "model"},
      "readings": [{"param": "V1", "value": "230.5", "unit": "V"}, ...]
    }

This adapter maps the meter's `param` names to our logical metric keys and
coerces stringified values to floats. Power values arrive in W and are
converted to kW because logical_metrics.yaml defines power metrics in kW.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from ..payloads import TelemetryPayload

# Acuvim param → (logical_metric_key, scale_factor).
# Scale converts the meter's unit to the logical_metric's unit:
#   - powers (Psum/Qsum/Ssum) arrive in W; we store kW → 0.001
#   - everything else is 1:1
PARAM_MAP: dict[str, tuple[str, float]] = {
    "V1":      ("voltage_l1_n",              1.0),
    "V2":      ("voltage_l2_n",              1.0),
    "V3":      ("voltage_l3_n",              1.0),
    "I1":      ("current_l1",                1.0),
    "I2":      ("current_l2",                1.0),
    "I3":      ("current_l3",                1.0),
    "Psum":    ("active_power_total",        0.001),
    "Qsum":    ("reactive_power_total",      0.001),
    "Ssum":    ("apparent_power_total",      0.001),
    "PF":      ("power_factor_total",        1.0),
    "Freq_Hz": ("frequency_hz",              1.0),
    "Ep_imp":  ("import_active_energy_kwh",  1.0),
    "Ep_exp":  ("export_active_energy_kwh",  1.0),
    # Non-numeric params (LoadType etc.) are skipped — TelemetryPayload only
    # carries numeric readings; enums go through a different ingestion path
    # (out of scope for the bench MVP).
}


def parse_acuvim_payload(
    raw: dict[str, Any], *, site_slug: str, device_id: UUID,
) -> TelemetryPayload:
    """Translate one AXM-WEB2 message into a validated TelemetryPayload.

    `site_slug` and `device_id` come from operator config — the meter's
    payload alone does not carry our internal IDs.
    """
    readings: dict[str, float] = {}
    for entry in raw.get("readings", []):
        param = entry.get("param")
        mapping = PARAM_MAP.get(param)
        if mapping is None:
            continue
        key, scale = mapping
        try:
            readings[key] = float(entry["value"]) * scale
        except (TypeError, ValueError):
            # Skip unparseable values rather than failing the whole batch.
            continue
    return TelemetryPayload(
        version="1.0",
        site_slug=site_slug,
        device_id=device_id,
        timestamp=raw["timestamp"],
        block="realtime",
        source="modbus_poll",
        quality="good",
        readings=readings,
    )
