"""Shared fixtures."""

from pathlib import Path

import pytest

from profile_loader import ProfileLoader

REPO_ROOT = Path(__file__).resolve().parents[3]
ARCH = REPO_ROOT / "architecture"


class _StubClockDecoder:
    """Stub for tests that don't exercise the real clock decoder."""

    def decode(self, buffer: bytes, offset: int, length_bytes: int) -> str:
        return "1970-01-01T00:00:00Z"


@pytest.fixture
def loader_with_stub_clock():
    loader = ProfileLoader()
    loader.register_decoder("acuvim_clock", _StubClockDecoder())
    return loader


@pytest.fixture
def loaded_acuvim_l(loader_with_stub_clock):
    catalog = loader_with_stub_clock.load_catalog(ARCH / "logical_metrics.yaml")
    profile = loader_with_stub_clock.load_profile(ARCH / "profiles" / "acuvim_l.yaml", catalog)
    return catalog, profile, loader_with_stub_clock.decoders
