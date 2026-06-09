import pytest


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_openapi(client):
    response = await client.get("/api/v1/openapi.json")
    assert response.status_code == 200
