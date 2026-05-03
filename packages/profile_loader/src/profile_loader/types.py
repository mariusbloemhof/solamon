"""Shared value-object and exception types."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


class ValidationError(Exception):
    """Raised when input fails validation. Message is operator-readable."""


class DecodeError(Exception):
    """Raised when a Modbus response can't be decoded according to the profile."""


class ProfileLoadError(Exception):
    """Raised when a profile YAML can't be parsed or fails cross-validation against the catalog."""


@dataclass(frozen=True)
class Reading:
    value: Any
    raw_value: int | None
    quality: Literal["good", "uncertain", "bad"]


@dataclass(frozen=True)
class FingerprintResult:
    match: bool
    confidence: Literal["positive", "negative_fingerprint", "none"]
    identifiers: dict[str, Any] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
