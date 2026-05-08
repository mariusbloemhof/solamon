"""Command handling and Modbus write/read-back acknowledgements."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from cachetools import TTLCache

from profile_loader.catalog import Catalog
from profile_loader.profile import Profile

from .buffer.store import Buffer
from .modbus.client import ModbusClient
from .modbus.codec import (
    decode_register_value,
    encode_register_value,
    register_count,
    values_equal,
)
from .now import now_utc
from .site_config import SiteConfig

log = structlog.get_logger()


@dataclass(frozen=True)
class CommandPayload:
    id: str
    site_slug: str
    device_id: str
    logical_metric: str
    type: str
    parameters: dict[str, Any]
    issued_at: str
    issued_by: str
    expires_at: str
    received_at: str

    @classmethod
    def from_json(cls, payload: bytes | str) -> CommandPayload:
        raw = json.loads(payload)
        required = {
            "id",
            "site_slug",
            "device_id",
            "logical_metric",
            "type",
            "parameters",
            "issued_at",
            "issued_by",
            "expires_at",
        }
        missing = required - set(raw)
        if missing:
            raise ValueError(f"missing command fields: {', '.join(sorted(missing))}")
        return cls(
            id=str(raw["id"]),
            site_slug=str(raw["site_slug"]),
            device_id=str(raw["device_id"]),
            logical_metric=str(raw["logical_metric"]),
            type=str(raw["type"]),
            parameters=dict(raw["parameters"]),
            issued_at=str(raw["issued_at"]),
            issued_by=str(raw["issued_by"]),
            expires_at=str(raw["expires_at"]),
            received_at=now_utc(),
        )


def _expired(expires_at: str) -> bool:
    return datetime.fromisoformat(expires_at.replace("Z", "+00:00")) < datetime.now(UTC)


def _ack(command: CommandPayload, site_config: SiteConfig, status: str, **fields: Any) -> dict[str, Any]:
    return {
        "version": "1.0",
        "id": command.id,
        "site_slug": site_config.site.slug,
        "device_id": site_config.device.id,
        "status": status,
        "received_at": command.received_at,
        "modbus_write_at": fields.get("modbus_write_at"),
        "readback_at": fields.get("readback_at"),
        "confirmed_value": fields.get("confirmed_value"),
        "error_message": fields.get("error_message"),
    }


async def publish_ack(client, site_config: SiteConfig, ack: dict[str, Any]) -> None:
    await client.publish(
        f"{site_config.mqtt.topic_prefix}/commands/{site_config.device.id}/ack",
        json.dumps(ack),
        qos=1,
    )
    log.info("command.ack_published", id=ack["id"], status=ack["status"])


async def handle_command(
    *,
    client,
    site_config: SiteConfig,
    profile: Profile,
    catalog: Catalog,
    modbus: ModbusClient,
    command: CommandPayload,
    recent: TTLCache[str, dict[str, Any]],
    buffer: Buffer | None = None,
    device_fault: str | None = None,
) -> dict[str, Any]:
    if command.id in recent:
        ack = recent[command.id]
        await publish_ack(client, site_config, ack)
        return ack
    if buffer is not None:
        persisted_ack = await buffer.get_processed_command_ack(command.id)
        if persisted_ack is not None:
            recent[command.id] = persisted_ack
            await publish_ack(client, site_config, persisted_ack)
            return persisted_ack
    if command.site_slug != site_config.site.slug or command.device_id != site_config.device.id:
        ack = _ack(command, site_config, "failed", error_message="site_or_device_mismatch")
        await _remember_command(buffer=buffer, recent=recent, command=command, ack=ack)
        await publish_ack(client, site_config, ack)
        return ack
    if command.type != "set_value":
        ack = _ack(command, site_config, "failed", error_message="command_type_not_supported")
        await _remember_command(buffer=buffer, recent=recent, command=command, ack=ack)
        await publish_ack(client, site_config, ack)
        return ack
    if _expired(command.expires_at):
        ack = _ack(command, site_config, "failed", error_message="received_after_expiry")
        await _remember_command(buffer=buffer, recent=recent, command=command, ack=ack)
        await publish_ack(client, site_config, ack)
        return ack
    if device_fault:
        ack = _ack(command, site_config, "failed", error_message=f"device_fault: {device_fault}")
        await _remember_command(buffer=buffer, recent=recent, command=command, ack=ack)
        await publish_ack(client, site_config, ack)
        return ack

    value = command.parameters.get("value")
    try:
        profile.validate_control(command.logical_metric, value, catalog)
        control = profile.control[command.logical_metric]
        encoded = encode_register_value(value, control.format)
        if control.fc == 6:
            if isinstance(encoded, list):
                raise ValueError("FC06 requires a single register value")
            result = await modbus.write_register(
                address=control.address,
                value=encoded,
                slave=site_config.device.unit_id,
            )
        elif control.fc == 16:
            values = encoded if isinstance(encoded, list) else [encoded]
            result = await modbus.write_registers(
                address=control.address,
                values=values,
                slave=site_config.device.unit_id,
            )
        else:
            raise ValueError(f"unsupported control fc: {control.fc}")
        if result.isError():
            ack = _ack(
                command,
                site_config,
                "failed",
                error_message=f"modbus_exception: {getattr(result, 'exception_code', None)}",
            )
            await _remember_command(buffer=buffer, recent=recent, command=command, ack=ack)
            await publish_ack(client, site_config, ack)
            return ack

        modbus_write_at = now_utc()
        rb = control.readback_register
        if rb is None:
            ack = _ack(
                command,
                site_config,
                "confirmed",
                modbus_write_at=modbus_write_at,
                confirmed_value={"value": value},
            )
            await _remember_command(buffer=buffer, recent=recent, command=command, ack=ack)
            await publish_ack(client, site_config, ack)
            return ack

        await asyncio.sleep(control.readback_delay_ms / 1000.0)
        if rb.fc == 3:
            rb_result = await modbus.read_holding_registers(
                address=rb.address,
                count=register_count(rb.format),
                slave=site_config.device.unit_id,
            )
        elif rb.fc == 4:
            rb_result = await modbus.read_input_registers(
                address=rb.address,
                count=register_count(rb.format),
                slave=site_config.device.unit_id,
            )
        else:
            raise ValueError(f"unsupported readback fc: {rb.fc}")
        readback_at = now_utc()
        if rb_result.isError():
            ack = _ack(
                command,
                site_config,
                "failed",
                modbus_write_at=modbus_write_at,
                readback_at=readback_at,
                error_message=f"readback_modbus_exception: {getattr(rb_result, 'exception_code', None)}",
            )
        else:
            actual = decode_register_value(rb_result.registers, rb.format)
            if values_equal(actual, value):
                ack = _ack(
                    command,
                    site_config,
                    "confirmed",
                    modbus_write_at=modbus_write_at,
                    readback_at=readback_at,
                    confirmed_value={"value": actual},
                )
            else:
                ack = _ack(
                    command,
                    site_config,
                    "failed",
                    modbus_write_at=modbus_write_at,
                    readback_at=readback_at,
                    confirmed_value={"value": actual},
                    error_message=f"readback_mismatch: expected={value}, got={actual}",
                )
    except Exception as exc:
        ack = _ack(command, site_config, "failed", error_message=str(exc))
    await _remember_command(buffer=buffer, recent=recent, command=command, ack=ack)
    await publish_ack(client, site_config, ack)
    return ack


async def _remember_command(
    *,
    buffer: Buffer | None,
    recent: TTLCache[str, dict[str, Any]],
    command: CommandPayload,
    ack: dict[str, Any],
) -> None:
    recent[command.id] = ack
    if buffer is not None:
        await buffer.record_processed_command(
            command_id=command.id,
            expires_at=command.expires_at,
            ack=ack,
        )
