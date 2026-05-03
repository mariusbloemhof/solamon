"""Solamon profile loader."""

from .catalog import Catalog, LogicalMetric
from .decoders import AcuvimClockDecoder, CustomDecoder, default_registry
from .fingerprint import ModbusClient
from .loader import ProfileLoader
from .profile import (
    ConnectionInfo,
    ControlSpec,
    DeviceInfo,
    Fingerprint,
    FingerprintIdentifier,
    FingerprintRead,
    MetricMap,
    Profile,
    ReadbackRegister,
    ReadBlock,
)
from .types import (
    DecodeError,
    FingerprintResult,
    ProfileLoadError,
    Reading,
    ValidationError,
)

__all__ = [
    "AcuvimClockDecoder",
    "Catalog",
    "ConnectionInfo",
    "ControlSpec",
    "CustomDecoder",
    "DecodeError",
    "DeviceInfo",
    "Fingerprint",
    "FingerprintIdentifier",
    "FingerprintRead",
    "FingerprintResult",
    "LogicalMetric",
    "MetricMap",
    "ModbusClient",
    "Profile",
    "ProfileLoadError",
    "ProfileLoader",
    "ReadBlock",
    "ReadbackRegister",
    "Reading",
    "ValidationError",
    "default_registry",
]
