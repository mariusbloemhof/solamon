"""Protocol and real pymodbus adapter."""

from __future__ import annotations

from typing import Protocol

from pymodbus.client import AsyncModbusTcpClient


class ModbusResult(Protocol):
    registers: list[int]
    exception_code: int

    def isError(self) -> bool: ...


class ModbusClient(Protocol):
    async def read_holding_registers(self, address: int, count: int, slave: int) -> ModbusResult: ...
    async def read_input_registers(self, address: int, count: int, slave: int) -> ModbusResult: ...
    async def write_register(self, address: int, value: int, slave: int) -> ModbusResult: ...
    async def write_registers(self, address: int, values: list[int], slave: int) -> ModbusResult: ...


def create_modbus_client(host: str, port: int) -> AsyncModbusTcpClient:
    return AsyncModbusTcpClient(
        host=host,
        port=port,
        timeout=5,
        retries=0,
        reconnect_delay=2,
        reconnect_delay_max=30,
    )
