import pytest

from profile_loader import ValidationError


def test_validate_control_passes_for_allowed_value(loaded_acuvim_l):
    catalog, profile, _ = loaded_acuvim_l
    profile.validate_control("demand_window_minutes", 30, catalog=catalog)
    profile.validate_control("demand_window_minutes", 1, catalog=catalog)


def test_validate_control_rejects_disallowed_value(loaded_acuvim_l):
    catalog, profile, _ = loaded_acuvim_l
    with pytest.raises(ValidationError, match="not in allowed"):
        profile.validate_control("demand_window_minutes", 99, catalog=catalog)


def test_validate_control_rejects_unknown_metric(loaded_acuvim_l):
    catalog, profile, _ = loaded_acuvim_l
    with pytest.raises(ValidationError, match="unknown"):
        profile.validate_control("not_a_metric", 1, catalog=catalog)


def test_validate_control_rejects_non_writable_metric(loaded_acuvim_l):
    catalog, profile, _ = loaded_acuvim_l
    with pytest.raises(ValidationError, match="not writable"):
        profile.validate_control("active_power_total", 12.5, catalog=catalog)


def test_validate_control_rejects_metric_not_in_profile_control_block():
    """Synthetic catalog + profile where a writable catalog metric is NOT in profile's control."""
    import yaml

    from profile_loader.catalog import Catalog
    from profile_loader.profile import Profile

    catalog = Catalog.from_dict(
        yaml.safe_load("""
schema_version: "1.0"
metrics:
  some_writable:
    label: Test
    unit: ""
    data_type: int
    category: control
    is_cumulative: false
    expected_range: [0, 100]
    is_writable: true
    allowed_values: [1, 2]
""")
    )
    profile = Profile.from_dict(
        {
            "schema_version": "1.0",
            "device": {"manufacturer": "Test", "model": "T", "category": "meter"},
            "connection": {"protocol": "modbus_tcp", "default_port": 502, "default_unit_id": 1},
            "fingerprint": {"reads": []},
            "read_blocks": [],
            # No control block — the metric is writable in catalog but not exposed here
        }
    )
    with pytest.raises(ValidationError, match="not exposed"):
        profile.validate_control("some_writable", 1, catalog=catalog)
