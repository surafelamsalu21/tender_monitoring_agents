"""Auth API: login, change password, super-admin user creation."""
from app.core.config import settings


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_patch_me_updates_full_name(client):
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": settings.DEFAULT_ADMIN_EMAIL,
            "password": settings.DEFAULT_ADMIN_PASSWORD,
        },
    ).json()
    token = login["access_token"]

    res = client.patch(
        "/api/v1/auth/me",
        json={"full_name": "  Display Name  "},
        headers=_headers(token),
    )
    assert res.status_code == 200
    assert res.json()["full_name"] == "Display Name"

    me = client.get("/api/v1/auth/me", headers=_headers(token))
    assert me.status_code == 200
    assert me.json()["full_name"] == "Display Name"


def test_login_bootstrap_super_admin(client):
    res = client.post(
        "/api/v1/auth/login",
        json={
            "email": settings.DEFAULT_ADMIN_EMAIL,
            "password": settings.DEFAULT_ADMIN_PASSWORD,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert "access_token" in body
    assert body["user"]["email"] == settings.DEFAULT_ADMIN_EMAIL.lower()
    assert body["user"]["role"] == "super_admin"


def test_change_password(client):
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": settings.DEFAULT_ADMIN_EMAIL,
            "password": settings.DEFAULT_ADMIN_PASSWORD,
        },
    ).json()
    token = login["access_token"]

    new_pw = "NewSecurePw999!"
    ch = client.post(
        "/api/v1/auth/change-password",
        json={"old_password": settings.DEFAULT_ADMIN_PASSWORD, "new_password": new_pw},
        headers=_headers(token),
    )
    assert ch.status_code == 200
    assert ch.json().get("success") is True

    bad = client.post(
        "/api/v1/auth/login",
        json={"email": settings.DEFAULT_ADMIN_EMAIL, "password": settings.DEFAULT_ADMIN_PASSWORD},
    )
    assert bad.status_code == 401

    ok = client.post(
        "/api/v1/auth/login",
        json={"email": settings.DEFAULT_ADMIN_EMAIL, "password": new_pw},
    )
    assert ok.status_code == 200


def test_super_admin_can_create_company_user(client):
    token = client.post(
        "/api/v1/auth/login",
        json={
            "email": settings.DEFAULT_ADMIN_EMAIL,
            "password": settings.DEFAULT_ADMIN_PASSWORD,
        },
    ).json()["access_token"]

    res = client.post(
        "/api/v1/admin/users",
        json={
            "email": "colleague@preciseethiopia.com",
            "password": "TempPass88!",
            "full_name": "Test Colleague",
            "role": "analyst",
        },
        headers=_headers(token),
    )
    assert res.status_code == 200
    assert res.json()["email"] == "colleague@preciseethiopia.com"
    assert res.json()["role"] == "analyst"

    user_login = client.post(
        "/api/v1/auth/login",
        json={"email": "colleague@preciseethiopia.com", "password": "TempPass88!"},
    )
    assert user_login.status_code == 200


def test_super_admin_can_reset_other_user_password(client):
    token_admin = client.post(
        "/api/v1/auth/login",
        json={
            "email": settings.DEFAULT_ADMIN_EMAIL,
            "password": settings.DEFAULT_ADMIN_PASSWORD,
        },
    ).json()["access_token"]

    client.post(
        "/api/v1/admin/users",
        json={
            "email": "resetme@preciseethiopia.com",
            "password": "OldPass88!",
            "role": "viewer",
        },
        headers=_headers(token_admin),
    )

    new_pw = "FreshPass999!"
    res = client.post(
        "/api/v1/admin/users/set-password",
        json={"email": "resetme@preciseethiopia.com", "new_password": new_pw},
        headers=_headers(token_admin),
    )
    assert res.status_code == 200
    assert res.json().get("success") is True

    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "resetme@preciseethiopia.com", "password": "OldPass88!"},
        ).status_code
        == 401
    )

    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "resetme@preciseethiopia.com", "password": new_pw},
        ).status_code
        == 200
    )


def test_super_admin_cannot_reset_own_password_via_admin_endpoint(client):
    token = client.post(
        "/api/v1/auth/login",
        json={
            "email": settings.DEFAULT_ADMIN_EMAIL,
            "password": settings.DEFAULT_ADMIN_PASSWORD,
        },
    ).json()["access_token"]

    denied = client.post(
        "/api/v1/admin/users/set-password",
        json={"email": settings.DEFAULT_ADMIN_EMAIL, "new_password": "Whatever99999!"},
        headers=_headers(token),
    )
    assert denied.status_code == 400


def test_non_super_admin_cannot_create_users(client):
    token_admin = client.post(
        "/api/v1/auth/login",
        json={
            "email": settings.DEFAULT_ADMIN_EMAIL,
            "password": settings.DEFAULT_ADMIN_PASSWORD,
        },
    ).json()["access_token"]

    client.post(
        "/api/v1/admin/users",
        json={
            "email": "viewer1@preciseethiopia.com",
            "password": "TempPass88!",
            "role": "viewer",
        },
        headers=_headers(token_admin),
    )

    token_viewer = client.post(
        "/api/v1/auth/login",
        json={"email": "viewer1@preciseethiopia.com", "password": "TempPass88!"},
    ).json()["access_token"]

    denied = client.post(
        "/api/v1/admin/users",
        json={
            "email": "blocked@preciseethiopia.com",
            "password": "TempPass88!",
            "role": "viewer",
        },
        headers=_headers(token_viewer),
    )
    assert denied.status_code == 403
