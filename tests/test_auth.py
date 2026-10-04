from datetime import UTC, datetime, timedelta

import jwt

from app.config import settings
from tests.conftest import login


async def test_register_login_me(client):
    headers = await login(client, "a@example.com")
    r = await client.get("/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["email"] == "a@example.com"


async def test_duplicate_email(client):
    cred = {"email": "a@example.com", "password": "password123"}
    assert (await client.post("/auth/register", json=cred)).status_code == 201
    assert (await client.post("/auth/register", json=cred)).status_code == 409


async def test_wrong_password_and_unknown_email_same_answer(client):
    await client.post("/auth/register", json={"email": "a@example.com", "password": "password123"})
    r1 = await client.post("/auth/login", json={"email": "a@example.com", "password": "wrong-pass"})
    r2 = await client.post("/auth/login", json={"email": "nobody@example.com", "password": "wrong-pass"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json() == r2.json()


async def test_missing_bad_and_expired_token(client):
    assert (await client.get("/auth/me")).status_code == 401
    bad = {"Authorization": "Bearer not-a-jwt"}
    assert (await client.get("/auth/me", headers=bad)).status_code == 401

    past = datetime.now(UTC) - timedelta(minutes=5)
    expired = jwt.encode({"sub": "1", "exp": past}, settings.jwt_secret, algorithm="HS256")
    r = await client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401


async def test_token_signed_with_other_key_rejected(client):
    await login(client, "a@example.com")
    future = datetime.now(UTC) + timedelta(minutes=5)
    forged = jwt.encode({"sub": "1", "exp": future}, "another-secret-another-secret-123", algorithm="HS256")
    r = await client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401
