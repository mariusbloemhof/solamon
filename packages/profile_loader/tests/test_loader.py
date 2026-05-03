from pathlib import Path

import pytest

from profile_loader import ProfileLoader, ProfileLoadError

REPO_ROOT = Path(__file__).resolve().parents[3]
ARCH = REPO_ROOT / "architecture"
CATALOG_PATH = ARCH / "logical_metrics.yaml"
ACUVIM_L_PATH = ARCH / "profiles" / "acuvim_l.yaml"


def test_load_catalog_returns_catalog_with_metrics():
    loader = ProfileLoader()
    catalog = loader.load_catalog(CATALOG_PATH)
    assert catalog.get("active_power_total") is not None
    assert len(catalog.all()) > 30


def test_load_profile_returns_validated_profile():
    loader = ProfileLoader()
    catalog = loader.load_catalog(CATALOG_PATH)
    profile = loader.load_profile(ACUVIM_L_PATH, catalog)
    assert profile.device.manufacturer == "AccuEnergy"
    assert len(profile.read_blocks) > 0


def test_load_profile_rejects_unknown_logical_metric(tmp_path: Path):
    loader = ProfileLoader()
    catalog = loader.load_catalog(CATALOG_PATH)
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
schema_version: "1.0"
device: { manufacturer: Test, model: TestUnit, category: meter }
connection: { protocol: modbus_tcp, default_port: 502, default_unit_id: 1 }
fingerprint:
  reads:
    - address: 0
      length: 2
      format: uint16
      expected_range: [0, 100]
read_blocks:
  - name: badblock
    fc: 3
    address: 0
    length: 4
    cadence_s: 10
    metrics:
      - { logical: this_metric_does_not_exist, offset: 0, format: float32_be }
""",
        encoding="utf-8",
    )
    with pytest.raises(ProfileLoadError, match="this_metric_does_not_exist"):
        loader.load_profile(bad, catalog)


def test_load_profile_rejects_offset_outside_block(tmp_path: Path):
    loader = ProfileLoader()
    catalog = loader.load_catalog(CATALOG_PATH)
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
schema_version: "1.0"
device: { manufacturer: Test, model: TestUnit, category: meter }
connection: { protocol: modbus_tcp, default_port: 502, default_unit_id: 1 }
fingerprint:
  reads:
    - address: 0
      length: 2
      format: uint16
      expected_range: [0, 100]
read_blocks:
  - name: realtime
    fc: 3
    address: 0
    length: 4
    cadence_s: 10
    metrics:
      - { logical: frequency_hz, offset: 12, format: float32_be }
""",
        encoding="utf-8",
    )
    with pytest.raises(ProfileLoadError, match="exceeds block length"):
        loader.load_profile(bad, catalog)


def test_load_profile_rejects_misaligned_offset(tmp_path: Path):
    loader = ProfileLoader()
    catalog = loader.load_catalog(CATALOG_PATH)
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
schema_version: "1.0"
device: { manufacturer: Test, model: TestUnit, category: meter }
connection: { protocol: modbus_tcp, default_port: 502, default_unit_id: 1 }
fingerprint:
  reads:
    - address: 0
      length: 2
      format: uint16
      expected_range: [0, 100]
read_blocks:
  - name: realtime
    fc: 3
    address: 0
    length: 4
    cadence_s: 10
    metrics:
      - { logical: frequency_hz, offset: 1, format: float32_be }
""",
        encoding="utf-8",
    )
    with pytest.raises(ProfileLoadError, match="alignment"):
        loader.load_profile(bad, catalog)


def test_load_profile_rejects_custom_format_without_registered_decoder(tmp_path: Path):
    loader = ProfileLoader()
    catalog = loader.load_catalog(CATALOG_PATH)
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
schema_version: "1.0"
device: { manufacturer: Test, model: TestUnit, category: meter }
connection: { protocol: modbus_tcp, default_port: 502, default_unit_id: 1 }
fingerprint:
  reads:
    - address: 0
      length: 2
      format: uint16
      expected_range: [0, 100]
read_blocks:
  - name: realtime
    fc: 3
    address: 0
    length: 8
    cadence_s: 10
    metrics:
      - { logical: meter_clock, offset: 0, format: custom, decoder: not_registered, length: 7 }
""",
        encoding="utf-8",
    )
    with pytest.raises(ProfileLoadError, match="not_registered"):
        loader.load_profile(bad, catalog)
