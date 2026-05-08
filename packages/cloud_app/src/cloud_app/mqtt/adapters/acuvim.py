"""AXM-WEB2 native payload → TelemetryPayload adapter.

The Acuvim L AXM-WEB2 publishes JSON with a shape that varies slightly
between firmware revisions. We've seen two top-level shapes in the wild:

Shape A — readings at top level (matches the spec doc example,
discovery/specs/acuvim_l_axm_web2_configuration.md §2.6):

    {
      "timestamp": "2025-09-15T10:30:00Z",     # or unix epoch int
      "gateway": {...},
      "device":  {...},
      "readings": [{"param": "V1", "value": "230.5", "unit": "V"}, ...]
    }

Shape B — readings nested inside `device` (Johan's bench, AXM-WEB2
firmware as of 2026-05-08):

    {
      "timestamp": 1778252253,                 # unix epoch (seconds)
      "gateway": {...},
      "device": {
        "name": "...", "model": "Acuvim-L", "serial": "...", "online": true,
        "readings": [{"param": "V1", "value": "0.000", "unit": "V"}, ...]
      }
    }

This adapter handles both shapes and maps the meter's `param` names to
our logical-metric keys, coercing stringified values to floats.

The `param` names also vary between firmware revisions:

  - Older / spec example: `Psum`, `Qsum`, `Ssum` (unit-less; values in W).
  - Newer (Johan's): `Psum_kW`, `Qsum_kvar`, `Ssum_kVA` (unit baked into
    the param name; values already in the named unit).

We map both. The scale factor takes care of the unit conversion in the
older form (W → kW = ×0.001).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from ..payloads import TelemetryPayload

# Acuvim param → (logical_metric_key, scale_factor).
# Scale converts the meter's published unit to the logical_metric's unit
# (logical_metrics.yaml stores power in kW, energy in kWh, etc.).
PARAM_MAP: dict[str, tuple[str, float]] = {
    # ─── Voltage (line-neutral) ─────────────────────────────────────────
    "V1":         ("voltage_l1_n",              1.0),
    "V2":         ("voltage_l2_n",              1.0),
    "V3":         ("voltage_l3_n",              1.0),

    # ─── Voltage (line-line) ────────────────────────────────────────────
    "V12":        ("voltage_l1_l2",             1.0),
    "V23":        ("voltage_l2_l3",             1.0),
    "V31":        ("voltage_l3_l1",             1.0),

    # ─── Current ────────────────────────────────────────────────────────
    "I1":         ("current_l1",                1.0),
    "I2":         ("current_l2",                1.0),
    "I3":         ("current_l3",                1.0),
    "In":         ("current_neutral",           1.0),

    # ─── Active power (per-phase + total) ───────────────────────────────
    # Newer firmware emits already-kW values with a `_kW` suffix.
    "P1":         ("active_power_l1",           1.0),
    "P2":         ("active_power_l2",           1.0),
    "P3":         ("active_power_l3",           1.0),
    "Psum":       ("active_power_total",        0.001),  # older: W
    "Psum_kW":    ("active_power_total",        1.0),    # newer: kW

    # ─── Reactive power (total only) ────────────────────────────────────
    "Qsum":       ("reactive_power_total",      0.001),  # older: var → kvar
    "Qsum_kvar":  ("reactive_power_total",      1.0),    # newer: kvar

    # ─── Apparent power (total only) ────────────────────────────────────
    "Ssum":       ("apparent_power_total",      0.001),  # older: VA → kVA
    "Ssum_kVA":   ("apparent_power_total",      1.0),    # newer: kVA

    # ─── Power factor ───────────────────────────────────────────────────
    "PF":         ("power_factor_total",        1.0),

    # ─── Frequency ──────────────────────────────────────────────────────
    "Freq_Hz":    ("frequency_hz",              1.0),

    # ─── Energy ─────────────────────────────────────────────────────────
    "Ep_imp":     ("import_active_energy_kwh",  1.0),
    "Ep_exp":     ("export_active_energy_kwh",  1.0),

    # Non-numeric params (LoadType, etc.) and per-phase reactive/apparent/
    # PF are dropped — they have no corresponding logical_metric key in
    # the current catalog. Adding them is a catalog-extension task.
}


def _extract_readings(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Find the readings array, accommodating both shape A (top-level) and
    shape B (nested under `device`)."""
    if isinstance(raw.get("readings"), list):
        return raw["readings"]
    device = raw.get("device")
    if isinstance(device, dict) and isinstance(device.get("readings"), list):
        return device["readings"]
    return []


def parse_acuvim_payload(
    raw: dict[str, Any], *, site_slug: str, device_id: UUID,
) -> TelemetryPayload:
    """Translate one AXM-WEB2 message into a validated TelemetryPayload.

    `site_slug` and `device_id` come from operator config — the meter's
    payload alone does not carry our internal IDs.
    """
    readings: dict[str, float] = {}
    for entry in _extract_readings(raw):
        if not isinstance(entry, dict):
            continue
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
