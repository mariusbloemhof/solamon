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


def test_validate_control_rejects_metric_not_in_profile_control_block(loaded_acuvim_l):
    catalog, profile, _ = loaded_acuvim_l
    writable = [m.key for m in catalog.all() if m.is_writable]
    not_in_profile = [w for w in writable if w not in profile.control]
    if not_in_profile:
        with pytest.raises(ValidationError, match="not exposed"):
            profile.validate_control(not_in_profile[0], 1, catalog=catalog)
