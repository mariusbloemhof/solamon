"""CLI entry point: `python -m profile_loader validate <profile-path>`.

Exits:
  0 — profile loaded + validated
  1 — invalid arguments
  2 — schema or cross-validation failure
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .loader import ProfileLoader
from .types import ProfileLoadError

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CATALOG = REPO_ROOT / "architecture" / "logical_metrics.yaml"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="solamon-profile-validate",
        description="Validate a Solamon device profile against the catalog + JSON Schema.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="Validate a single profile.")
    v.add_argument("profile", type=Path)
    v.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    args = parser.parse_args(argv)

    if args.cmd == "validate":
        loader = ProfileLoader()
        try:
            catalog = loader.load_catalog(args.catalog)
            profile = loader.load_profile(args.profile, catalog)
        except ProfileLoadError as e:
            print(f"✗ {e}", file=sys.stderr)
            return 2
        n_metrics = sum(len(b.metrics) for b in profile.read_blocks)
        print(f"OK: {profile.device.manufacturer} / {profile.device.model} ({profile.device.category})")
        print(f"   {len(profile.read_blocks)} read block(s); {n_metrics} metric(s) total")
        print(f"   {len(profile.control)} control register(s)")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
