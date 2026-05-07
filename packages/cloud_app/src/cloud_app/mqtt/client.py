"""MQTT client wrapper.

SOLID-D + I: domain code accepts an MqttClient Protocol; tests pass fakes.
"""
from __future__ import annotations

import json
from typing import Any, AsyncIterator, Protocol


class MqttClient(Protocol):
    async def publish(self, topic: str, payload: bytes | str, qos: int = 1, retain: bool = False) -> None: ...
    async def subscribe(self, topic_filter: str, qos: int = 1) -> None: ...
    def messages(self) -> AsyncIterator[Any]: ...


def encode_payload(obj: dict[str, Any]) -> bytes:
    return json.dumps(obj, default=str, separators=(",", ":")).encode("utf-8")


def decode_payload(raw: bytes) -> dict[str, Any]:
    return json.loads(raw.decode("utf-8"))
