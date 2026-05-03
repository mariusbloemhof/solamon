"""Smoke tests: package imports + every name in __all__ resolves."""


def test_can_import_profile_loader():
    import profile_loader

    assert profile_loader.__name__ == "profile_loader"


def test_all_public_names_resolve():
    """Every name in __all__ must actually be importable from the package."""
    import profile_loader

    for name in profile_loader.__all__:
        assert hasattr(profile_loader, name), f"{name!r} listed in __all__ but not importable"
