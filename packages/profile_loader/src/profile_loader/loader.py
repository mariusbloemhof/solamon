"""Top-level loader: parse + validate catalog and profiles.

Spec: docs/specs/device-library/profile-schema.md §7-8
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from jsonschema import Draft202012Validator

from .catalog import Catalog
from .profile import Profile
from .types import ProfileLoadError

if TYPE_CHECKING:
    from .decoders import CustomDecoder

# Workspace-checkout layout: packages/profile_loader/src/profile_loader/loader.py
# → repo root is parents[4]. This works for `pip install -e packages/profile_loader`
# from the repo root (the only supported install pattern in MVP). Distribution via
# PyPI is post-MVP; when it lands, schemas will be bundled inside the package via
# importlib.resources.
DEFAULT_SCHEMA_DIR = Path(__file__).resolve().parents[4] / "architecture"

FORMAT_BYTES: dict[str, int] = {
    "float32_be": 4,
    "float32_le": 4,
    "float32_mb": 4,
    "uint16": 2,
    "int16": 2,
    "word": 2,
    "uint32_be": 4,
    "int32_be": 4,
    "dword_high_first": 4,
    "ascii": 0,
    "custom": 0,
}

FORMAT_ALIGN: dict[str, int] = {
    "float32_be": 4,
    "float32_le": 4,
    "float32_mb": 4,
    "uint32_be": 4,
    "int32_be": 4,
    "dword_high_first": 4,
    "uint16": 2,
    "int16": 2,
    "word": 2,
    "ascii": 1,
    "custom": 1,
}


class ProfileLoader:
    """Loads + validates profile YAMLs and the logical-metric catalog."""

    def __init__(
        self,
        schema_dir: Path | None = None,
        decoders: dict[str, CustomDecoder] | None = None,
    ) -> None:
        from .decoders import default_registry

        self._schema_dir = (schema_dir or DEFAULT_SCHEMA_DIR).resolve()
        if not self._schema_dir.exists():
            raise ProfileLoadError(
                f"schema dir not found: {self._schema_dir}. "
                "Pass schema_dir=Path(...) to ProfileLoader() if running outside "
                "the workspace checkout. (Distribution via PyPI is post-MVP.)"
            )
        self._decoders = decoders if decoders is not None else default_registry()

    def register_decoder(self, name: str, decoder: Any) -> None:
        self._decoders[name] = decoder

    @property
    def decoders(self) -> dict[str, Any]:
        return self._decoders

    def load_catalog(self, path: str | Path) -> Catalog:
        path = Path(path)
        raw = _load_yaml(path)
        _validate_jsonschema(raw, self._schema_dir / "logical_metrics.schema.json", path)
        return Catalog.from_dict(raw)

    def load_profile(self, path: str | Path, catalog: Catalog) -> Profile:
        path = Path(path)
        raw = _load_yaml(path)
        _validate_jsonschema(raw, self._schema_dir / "profiles" / "profile.schema.json", path)
        profile = Profile.from_dict(raw)
        self._cross_validate(profile, catalog, path)
        return profile

    def _cross_validate(self, profile: Profile, catalog: Catalog, path: Path) -> None:
        for block in profile.read_blocks:
            block_byte_length = block.length * 2
            for metric in block.metrics:
                if catalog.get(metric.logical) is None:
                    raise ProfileLoadError(
                        f"{path}: read_block '{block.name}': metric '{metric.logical}' not in catalog"
                    )
                if metric.format not in FORMAT_BYTES:
                    raise ProfileLoadError(
                        f"{path}: metric '{metric.logical}': unknown format '{metric.format}'"
                    )
                align = FORMAT_ALIGN[metric.format]
                if metric.offset % align != 0:
                    raise ProfileLoadError(
                        f"{path}: metric '{metric.logical}': offset {metric.offset} "
                        f"violates {align}-byte alignment for format '{metric.format}'"
                    )
                if metric.format == "ascii":
                    if metric.length is None:
                        raise ProfileLoadError(
                            f"{path}: metric '{metric.logical}': format 'ascii' requires 'length'"
                        )
                    end = metric.offset + (metric.length * 2)
                elif metric.format == "custom":
                    end = metric.offset + ((metric.length or 1) * 2)
                else:
                    end = metric.offset + FORMAT_BYTES[metric.format]
                if end > block_byte_length:
                    raise ProfileLoadError(
                        f"{path}: metric '{metric.logical}': bytes {metric.offset}-{end} "
                        f"exceeds block length {block_byte_length} bytes"
                    )
                if metric.format == "custom":
                    if metric.decoder is None:
                        raise ProfileLoadError(
                            f"{path}: metric '{metric.logical}': format 'custom' requires 'decoder'"
                        )
                    if metric.length is None:
                        raise ProfileLoadError(
                            f"{path}: metric '{metric.logical}': format 'custom' requires 'length'"
                        )
                    if metric.decoder not in self._decoders:
                        raise ProfileLoadError(
                            f"{path}: metric '{metric.logical}': decoder '{metric.decoder}' not registered"
                        )

        for control_key in profile.control:
            cm = catalog.get(control_key)
            if cm is None:
                raise ProfileLoadError(f"{path}: control '{control_key}' not in catalog")
            if not cm.is_writable:
                raise ProfileLoadError(f"{path}: control '{control_key}' not marked is_writable")


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise ProfileLoadError(f"file not found: {path}")
    with path.open(encoding="utf-8") as f:
        try:
            return yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ProfileLoadError(f"{path}: YAML parse error: {e}") from e


def _validate_jsonschema(raw: dict, schema_path: Path, source_path: Path) -> None:
    with schema_path.open(encoding="utf-8") as f:
        schema = json.load(f)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(raw), key=lambda e: list(e.absolute_path))
    if errors:
        msgs = "; ".join(f"{list(e.absolute_path)}: {e.message}" for e in errors)
        raise ProfileLoadError(f"{source_path}: schema violations: {msgs}")
