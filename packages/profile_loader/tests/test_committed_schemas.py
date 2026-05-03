# packages/profile_loader/tests/test_committed_schemas.py
"""Validate the committed architecture/*.yaml files against their JSON Schemas.

If these tests fail, the YAML and schema have drifted and NO downstream code
(edge agent, cloud, probe) will work correctly.
"""
import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[3]
ARCH = REPO_ROOT / "architecture"


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _validate(raw: dict, schema_path: Path) -> list[str]:
    schema = _load_json(schema_path)
    validator = Draft202012Validator(schema)
    return [
        f"{list(e.absolute_path)}: {e.message}"
        for e in sorted(validator.iter_errors(raw), key=lambda e: list(e.absolute_path))
    ]


def test_logical_metrics_yaml_conforms_to_schema():
    errors = _validate(_load_yaml(ARCH / "logical_metrics.yaml"), ARCH / "logical_metrics.schema.json")
    assert errors == [], "\n".join(errors)


def test_acuvim_l_profile_conforms_to_schema():
    errors = _validate(_load_yaml(ARCH / "profiles" / "acuvim_l.yaml"), ARCH / "profiles" / "profile.schema.json")
    assert errors == [], "\n".join(errors)


def test_logical_metrics_yaml_loads_as_dict():
    catalog = _load_yaml(ARCH / "logical_metrics.yaml")
    assert isinstance(catalog, dict)
    # v1.1+ shape: top-level wrapper with `metrics` key.
    assert "active_power_total" in catalog["metrics"]
