import pytest
from uuid import UUID


@pytest.mark.asyncio
async def test_list_sites_returns_organisation_sites(api_client, admin_token, seed_site):
    res = await api_client.get("/api/v1/sites",
                               headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    sites = res.json()
    assert len(sites) >= 1
    assert any(s["slug"] == seed_site.slug for s in sites)


@pytest.mark.asyncio
async def test_get_site_returns_detail_with_devices(api_client, admin_token, seed_site, seed_device):
    res = await api_client.get(f"/api/v1/sites/{seed_site.slug}",
                               headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    body = res.json()
    assert body["slug"] == seed_site.slug
    assert len(body["devices"]) >= 1


@pytest.mark.asyncio
async def test_get_unknown_site_returns_404(api_client, admin_token):
    res = await api_client.get("/api/v1/sites/no-such-site",
                               headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 404
