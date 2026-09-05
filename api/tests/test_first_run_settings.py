from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import auth, main, routes
from app.database import Base, get_db
from app.models import AppSettings, User


@pytest.fixture()
def fresh_client(tmp_path: Path, monkeypatch):
    auth._attempts.clear()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(engine)
    auth.settings.jwt_secret = "first-run-test-secret"
    main.settings.media_root = tmp_path / "media"
    main.settings.backup_root = tmp_path / "backups"
    routes.settings.media_root = main.settings.media_root
    monkeypatch.setattr(routes.prepare_media, "delay", lambda asset_id: None)

    def override_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[get_db] = override_db
    with TestClient(main.app) as client:
        yield client, session_factory
    main.app.dependency_overrides.clear()


def setup_payload(**changes):
    payload = {
        "organization_name": "Signal Test School",
        "display_name": "Signal Administrator",
        "username": "Admin",
        "password": "SIGNAL#1",
        "password_confirmation": "SIGNAL#1",
    }
    payload.update(changes)
    return payload


def test_fresh_install_setup_creates_admin_settings_and_session(fresh_client):
    client, session_factory = fresh_client
    assert client.get("/api/v1/setup/status").json() == {"setup_required": True, "organization_name": None, "playlists_enabled": False}

    response = client.post("/api/v1/setup", json=setup_payload())
    assert response.status_code == 201
    result = response.json()
    assert result["user"]["super_admin"] is True
    assert result["user"]["username"] == "admin"
    assert result["settings"]["organization_name"] == "Signal Test School"
    assert result["settings"]["playlists_enabled"] is False
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {result['access_token']}"}).status_code == 200
    assert client.get("/api/v1/setup/status").json() == {"setup_required": False, "organization_name": "Signal Test School", "playlists_enabled": False}

    with session_factory() as db:
        saved = db.get(AppSettings, 1)
        assert saved and saved.setup_completed_at
        assert db.query(User).count() == 1
        assert "SIGNAL#1" not in db.scalar(db.query(User.password_hash).statement)


def test_setup_is_one_time_and_password_policy_is_authoritative(fresh_client):
    client, session_factory = fresh_client
    bad = client.post("/api/v1/setup", json=setup_payload(password="signal#1", password_confirmation="signal#1"))
    assert bad.status_code == 422
    assert "uppercase" in bad.json()["detail"].lower()
    assert client.post("/api/v1/setup", json=setup_payload()).status_code == 201
    assert client.post("/api/v1/setup", json=setup_payload(username="second")).status_code == 409
    with session_factory() as db:
        assert db.query(User).count() == 1


@pytest.mark.parametrize("password,valid", [
    ("SIGNAL#1", True),
    ("Sig#1", False),
    ("signal#1", False),
    ("SIGNAL#!", False),
    ("SIGNAL12", False),
])
def test_password_policy(password, valid):
    assert (auth.password_policy_error(password) is None) is valid


def test_existing_user_install_is_not_sent_to_setup(fresh_client):
    client, session_factory = fresh_client
    with session_factory() as db:
        db.add(User(username="existing", display_name="Existing", password_hash=auth.hash_password("legacy password"), super_admin=True))
        db.commit()
    assert client.get("/api/v1/setup/status").json() == {"setup_required": False, "organization_name": "Signal", "playlists_enabled": False}
    with session_factory() as db:
        assert db.get(AppSettings, 1).setup_completed_at is not None


def test_settings_authorization_and_validation(fresh_client):
    client, _ = fresh_client
    setup = client.post("/api/v1/setup", json=setup_payload()).json()
    headers = {"Authorization": f"Bearer {setup['access_token']}"}
    assert client.get("/api/v1/settings", headers=headers).json()["default_slide_duration_seconds"] == 20
    assert client.get("/api/v1/settings", headers=headers).json()["playlists_enabled"] is False
    updated = client.patch("/api/v1/settings", headers=headers, json={"organization_name": "North Campus", "timezone": "America/New_York", "default_slide_duration_seconds": 15, "playlists_enabled": True})
    assert updated.status_code == 200
    assert updated.json() == {"organization_name": "North Campus", "timezone": "America/New_York", "default_slide_duration_seconds": 15, "playlists_enabled": True}
    assert client.patch("/api/v1/settings", headers=headers, json={"timezone": "Not/A_Timezone"}).status_code == 422
    assert client.get("/api/v1/settings").status_code == 401


def test_password_policy_applies_to_user_creation_reset_and_change(fresh_client):
    client, _ = fresh_client
    setup = client.post("/api/v1/setup", json=setup_payload()).json()
    headers = {"Authorization": f"Bearer {setup['access_token']}"}
    invalid_user = client.post("/api/v1/users", headers=headers, json={"username": "person", "display_name": "Person", "password": "signal#1"})
    assert invalid_user.status_code == 422
    created = client.post("/api/v1/users", headers=headers, json={"username": "person", "display_name": "Person", "password": "PERSON#1"})
    assert created.status_code == 201
    assert client.post(f"/api/v1/users/{created.json()['id']}/reset-password", headers=headers, json={"password": "SIGNAL12"}).status_code == 422
    assert client.post("/api/v1/auth/change-password", headers=headers, json={"password": "SIGNAL12"}).status_code == 422
