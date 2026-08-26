from base64 import b64decode
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import auth, main, routes
from app.database import Base, get_db
from app.models import AuditEvent, Building, PermissionGrant, Player, User


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    auth._attempts.clear()
    auth._enrollment_attempts.clear()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(engine)
    auth.settings.jwt_secret = "test-secret"
    main.settings.media_root = tmp_path / "media"
    routes.settings.media_root = main.settings.media_root
    main.settings.backup_root = tmp_path / "backups"
    monkeypatch.setattr(routes.prepare_media, "delay", lambda asset_id: None)

    def override_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[get_db] = override_db
    with session_factory() as db:
        high = Building(name="High School")
        middle = Building(name="Middle School")
        admin = User(username="admin", display_name="Admin", password_hash=auth.hash_password("a-long-test-password"), super_admin=True)
        kitchen = User(username="kitchen", display_name="Kitchen User", password_hash=auth.hash_password("a-long-test-password"))
        disabled = User(username="disabled", display_name="Disabled User", password_hash=auth.hash_password("a-long-test-password"), enabled=False)
        db.add_all([high, middle, admin, kitchen, disabled]); db.flush()
        cafeteria = Player(name="HS Cafeteria", building_id=high.id)
        middle_lobby = Player(name="MS Lobby", building_id=middle.id)
        db.add_all([cafeteria, middle_lobby]); db.flush()
        db.add_all([PermissionGrant(user_id=kitchen.id, capability="view", scope_type="player", scope_id=cafeteria.id), PermissionGrant(user_id=kitchen.id, capability="upload_media", scope_type="player", scope_id=cafeteria.id)])
        db.commit()
        ids = {"high": high.id, "cafeteria": cafeteria.id}
    with TestClient(main.app) as test_client:
        yield test_client, ids
    main.app.dependency_overrides.clear()


def login(client: TestClient, username: str, password: str = "a-long-test-password") -> str:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_authentication_and_protected_endpoint(client):
    test_client, _ = client
    assert test_client.get("/api/v1/players").status_code == 401
    assert test_client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401
    assert test_client.post("/api/v1/auth/login", json={"username": "disabled", "password": "a-long-test-password"}).status_code == 401
    token = login(test_client, "admin")
    assert test_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["super_admin"] is True


def test_scoped_visibility_and_write_protection(client):
    test_client, ids = client
    admin_token = login(test_client, "admin")
    kitchen_token = login(test_client, "kitchen")
    kitchen_headers = {"Authorization": f"Bearer {kitchen_token}"}
    assert len(test_client.get("/api/v1/players", headers={"Authorization": f"Bearer {admin_token}"}).json()) == 2
    visible = test_client.get("/api/v1/players", headers=kitchen_headers).json()
    assert [item["id"] for item in visible] == [ids["cafeteria"]]
    buildings = test_client.get("/api/v1/buildings", headers=kitchen_headers).json()
    assert [item["id"] for item in buildings] == [ids["high"]]
    denied = test_client.post("/api/v1/players", headers=kitchen_headers, json={"name": "Not allowed", "building_id": ids["high"], "enabled": True})
    assert denied.status_code == 403


def test_permitted_media_upload_is_persistent(client):
    test_client, ids = client
    token = login(test_client, "kitchen")
    tiny_png = b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLqNwAAAABJRU5ErkJggg==")
    response = test_client.post("/api/v1/media/upload", headers={"Authorization": f"Bearer {token}"}, data={"scope_type": "player", "scope_id": ids["cafeteria"]}, files=[("files", ("lunch-menu.png", tiny_png, "image/png"))])
    assert response.status_code == 201
    asset = response.json()[0]
    assert asset["processing_state"] == "processing"
    assert test_client.get("/api/v1/media", headers={"Authorization": f"Bearer {token}"}).json()[0]["id"] == asset["id"]


def test_admin_can_create_building_and_manual_player_with_audit(client):
    test_client, _ = client
    token = login(test_client, "admin")
    headers = {"Authorization": f"Bearer {token}"}
    building = test_client.post("/api/v1/buildings", headers=headers, json={"name": "Regression Academy", "description": "Created by regression", "enabled": True})
    assert building.status_code == 201
    player = test_client.post("/api/v1/players", headers=headers, json={"name": "Regression Lobby", "building_id": building.json()["id"], "description": "Front entry", "enabled": True})
    assert player.status_code == 201
    assert player.json()["health_state"] == "never_connected"
    events = test_client.get("/api/v1/audit", headers=headers).json()
    assert {"building.created", "player.created"}.issubset({event["action"] for event in events})


def test_admin_can_edit_and_delete_player(client):
    test_client, ids = client
    headers = {"Authorization": f"Bearer {login(test_client, 'admin')}"}
    updated = test_client.patch(
        f"/api/v1/players/{ids['cafeteria']}",
        headers=headers,
        json={
            "name": "Cafeteria Display",
            "building_id": ids["high"],
            "description": "Serving line",
            "enabled": False,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Cafeteria Display"
    assert updated.json()["enabled"] is False
    removed = test_client.delete(f"/api/v1/players/{ids['cafeteria']}", headers=headers)
    assert removed.status_code == 200
    assert removed.json()["ok"] is True
    assert ids["cafeteria"] not in {
        player["id"]
        for player in test_client.get("/api/v1/players", headers=headers).json()
    }
    events = test_client.get("/api/v1/audit", headers=headers).json()
    assert "player.archived" in {event["action"] for event in events}


def test_empty_building_can_be_archived_but_a_building_with_displays_cannot(client):
    test_client, ids = client
    headers = {"Authorization": f"Bearer {login(test_client, 'admin')}"}
    empty = test_client.post("/api/v1/buildings", headers=headers, json={"name": "Empty Regression Building", "enabled": True}).json()
    assert test_client.delete(f"/api/v1/buildings/{empty['id']}", headers=headers).status_code == 200
    assert empty["id"] not in {item["id"] for item in test_client.get("/api/v1/buildings", headers=headers).json()}
    blocked = test_client.delete(f"/api/v1/buildings/{ids['high']}", headers=headers)
    assert blocked.status_code == 409
    assert "contains 1 display" in blocked.json()["detail"]


def test_archiving_enrolled_player_revokes_access_and_preserves_history(client):
    test_client, ids = client
    headers = {"Authorization": f"Bearer {login(test_client, 'admin')}"}
    prepared = test_client.post(
        "/api/v1/players/prepare-enrollment",
        headers=headers,
        json={"name": "Archive Me", "building_id": ids["high"], "enabled": True},
    ).json()
    credentials = test_client.post(
        "/api/v1/device/enroll",
        json={"code": prepared["enrollment"]["code"], "device_identifier": "archive-device-001"},
    ).json()
    player_id = prepared["player"]["id"]
    assert test_client.delete(f"/api/v1/players/{player_id}", headers=headers).status_code == 200
    device_headers = {
        "X-Signal-Player-ID": credentials["player_id"],
        "X-Signal-Player-Secret": credentials["device_secret"],
    }
    assert test_client.get("/api/v1/player-agent/manifest", headers=device_headers).status_code == 401
    assert player_id not in {item["id"] for item in test_client.get("/api/v1/players", headers=headers).json()}
    events = test_client.get("/api/v1/audit", headers=headers).json()
    assert any(event["action"] == "player.archived" and event["resource_id"] == player_id for event in events)


def test_unauthorized_player_removal_is_denied(client):
    test_client, ids = client
    headers = {"Authorization": f"Bearer {login(test_client, 'kitchen')}"}
    assert test_client.delete(f"/api/v1/players/{ids['cafeteria']}", headers=headers).status_code == 403
