"""Display-time formatting helpers shared between consumers (web-ui, probe-cli, profile editor).

Spec: docs/specs/web-ui/pages.md §9 (hex address allowlist), cloud review #14.
"""

from __future__ import annotations


def format_address(n: int) -> str:
    """Render a Modbus register address as `0x____` (uppercase hex, 4-digit min)."""
    return f"0x{n:04X}"


# Fields in profile YAML / probe output JSON that are register addresses and
# should be rendered as hex. Consumers (admin profile-detail page, probe output
# view) iterate the parsed structure and apply format_address() to these fields
# only — NOT to other integer fields like length, cadence_s, offset.
ADDRESS_FIELDS: frozenset[str] = frozenset(
    {
        "address",  # read_blocks[].address, fingerprint.reads[].address,
        # fingerprint.identifiers[].address, control[].address
        "readback_register.address",
    }
)
