import pytest


@pytest.mark.asyncio
async def test_login_returns_jwt_for_valid_credentials(api_client, seed_admin):
    res = await api_client.post("/api/v1/auth/login",
                                json={"email": seed_admin.email, "password": "hunter2"})
    assert res.status_code == 200
    body = res.json()
    assert body["token_type"] == "bearer"
    assert "access_token" in body
    assert body["user"]["email"] == seed_admin.email


@pytest.mark.asyncio
async def test_login_rejects_invalid_credentials(api_client, seed_admin):
    res = await api_client.post("/api/v1/auth/login",
                                json={"email": seed_admin.email, "password": "wrong"})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_current_user(api_client, admin_token, seed_admin):
    res = await api_client.get("/api/v1/auth/me",
                               headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    assert res.json()["email"] == seed_admin.email


@pytest.mark.asyncio
async def test_me_returns_401_without_token(api_client):
    res = await api_client.get("/api/v1/auth/me")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_401_with_bad_token(api_client):
    res = await api_client.get("/api/v1/auth/me",
                               headers={"Authorization": "Bearer not.a.jwt"})
    assert res.status_code == 401
