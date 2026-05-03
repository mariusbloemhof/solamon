import yaml

from profile_loader.catalog import Catalog, LogicalMetric


SAMPLE = """
active_power_total:
  label: "Total active power"
  unit: kW
  data_type: float
  category: power
  is_cumulative: false
  direction_convention: "positive = consumption"
  expected_range: [-2000, 2000]

demand_window_minutes:
  label: "Demand integration window"
  unit: min
  data_type: int
  category: configuration
  is_cumulative: false
  expected_range: [1, 60]
  is_writable: true
  allowed_values: [1, 5, 10, 15, 30]
"""


def test_catalog_from_dict_parses_metrics():
    catalog = Catalog.from_dict(yaml.safe_load(SAMPLE))
    apt = catalog.get("active_power_total")
    assert isinstance(apt, LogicalMetric)
    assert apt.unit == "kW"
    assert apt.data_type == "float"
    assert apt.is_writable is False
    dwm = catalog.get("demand_window_minutes")
    assert dwm.is_writable is True
    assert dwm.allowed_values == [1, 5, 10, 15, 30]


def test_catalog_get_returns_none_for_unknown_metric():
    catalog = Catalog.from_dict(yaml.safe_load(SAMPLE))
    assert catalog.get("not_a_metric") is None


def test_catalog_all_returns_every_metric():
    catalog = Catalog.from_dict(yaml.safe_load(SAMPLE))
    assert {m.key for m in catalog.all()} == {"active_power_total", "demand_window_minutes"}


def test_logical_metric_is_frozen():
    """SOLID: value objects are immutable."""
    import pytest
    catalog = Catalog.from_dict(yaml.safe_load(SAMPLE))
    apt = catalog.get("active_power_total")
    with pytest.raises((AttributeError, Exception)):  # FrozenInstanceError
        apt.unit = "MW"
