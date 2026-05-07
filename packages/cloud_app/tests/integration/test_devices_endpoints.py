from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_list_devices_returns_site_devices(api_client, admin_token, seed_site, seed_device):
    res = await api_client.get(
        f"/api/v1/sites/{seed_site.slug}/devices",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    devices = res.json()
    assert len(devices) >= 1
    assert any(d["name"] == seed_device.name for d in devices)


@pytest.mark.asyncio
async def test_get_device_returns_detail(api_client, admin_token, seed_site, seed_device):
    res = await api_client.get(
        f"/api/v1/sites/{seed_site.slug}/devices/{seed_device.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == seed_device.name
    assert body["manufacturer"] == "AccuEnergy"
    assert body["model"] == "Acuvim L"
    assert body["profile_slug"] == "acuvim_l"


@pytest.mark.asyncio
async def test_get_unknown_device_returns_404(api_client, admin_token, seed_site):
    res = await api_client.get(
        f"/api/v1/sites/{seed_site.slug}/devices/{uuid4()}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 404
