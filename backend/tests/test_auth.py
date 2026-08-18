import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.user import User


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client


def unique_email() -> str:
    return f"test-{uuid.uuid4().hex}@example.com"


@pytest.mark.asyncio
async def test_register_user(client):
    email = unique_email()

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "TestPassword123",
            "full_name": "Auth Test User",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["email"] == email
    assert data["is_active"] is True
    assert data["is_verified"] is False
    assert "password" not in data
    assert "password_hash" not in data


@pytest.mark.asyncio
async def test_duplicate_registration_returns_409(client):
    email = unique_email()

    payload = {
        "email": email,
        "password": "TestPassword123",
        "full_name": "Duplicate Test",
    }

    first_response = await client.post(
        "/api/v1/auth/register",
        json=payload,
    )

    assert first_response.status_code == 201

    second_response = await client.post(
        "/api/v1/auth/register",
        json=payload,
    )

    assert second_response.status_code == 409


@pytest.mark.asyncio
async def test_login_returns_access_token(client):
    email = unique_email()

    await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "TestPassword123",
        },
    )

    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "TestPassword123",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["token_type"] == "bearer"
    assert data["access_token"]


@pytest.mark.asyncio
async def test_login_with_wrong_password_returns_401(client):
    email = unique_email()

    await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "TestPassword123",
        },
    )

    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "WrongPassword123",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


@pytest.mark.asyncio
async def test_me_requires_authentication(client):
    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_with_invalid_token_returns_401(client):
    response = await client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": "Bearer invalid-token",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_authenticated_user(client):
    email = unique_email()

    register_response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "TestPassword123",
            "full_name": "Authenticated User",
        },
    )

    assert register_response.status_code == 201

    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "TestPassword123",
        },
    )

    assert login_response.status_code == 200

    token = login_response.json()["access_token"]

    me_response = await client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert me_response.status_code == 200

    data = me_response.json()

    assert data["email"] == email
    assert data["is_active"] is True
    assert data["is_verified"] is False