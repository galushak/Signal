from app import routes
from test_functional_core import client, login


def prepare(test_client, headers, building_id, name="TEST PI"):
    response = test_client.post(
        "/api/v1/players/prepare-enrollment",
        headers=headers,
        json={"name": name, "building_id": building_id, "description": "Lab", "enabled": True},
    )
    assert response.status_code == 201
    return response.json()


def enroll_device(test_client, code, identifier="test-device-0001"):
    return test_client.post(
        "/api/v1/device/enroll",
        json={"code": code, "device_identifier": identifier, "software_version": "0.1.0"},
    )


def test_server_generated_enrollment_is_single_use_and_device_protocol_works(client):
    test_client, ids = client
    headers = {"Authorization": f"Bearer {login(test_client, 'admin')}"}
    prepared = prepare(test_client, headers, ids["high"])
    code = prepared["enrollment"]["code"]
    assert code.count("-") == 1
    denied = test_client.post("/api/v1/players/prepare-enrollment", headers={"Authorization": f"Bearer {login(test_client, 'kitchen')}"}, json={"name": "Denied", "building_id": ids["high"]})
    assert denied.status_code == 403
    credentials = enroll_device(test_client, code).json()
    assert credentials["player_id"] == prepared["player"]["id"]
    assert "device_secret" in credentials
    assert enroll_device(test_client, code, "test-device-0002").status_code == 409
    device_headers = {"X-Signal-Player-ID": credentials["player_id"], "X-Signal-Player-Secret": credentials["device_secret"]}
    heartbeat = test_client.post("/api/v1/player-agent/heartbeat", headers=device_headers, json={"software_version": "0.1.0", "renderer_status": "running", "cache_state": "ready", "temperature": "unsupported"})
    assert heartbeat.status_code == 200
    manifest = test_client.get("/api/v1/player-agent/manifest", headers=device_headers)
    assert manifest.status_code == 200
    assert test_client.get("/api/v1/player-agent/manifest", headers={**device_headers, "If-None-Match": manifest.headers["etag"]}).status_code == 304
    events = test_client.get("/api/v1/audit", headers=headers).json()
    assert any(event["action"] == "player.enrollment_prepared" for event in events)
    assert any(event["action"] == "player.device_enrolled" for event in events)


def test_regeneration_cancellation_and_expiry_invalidate_codes(client):
    test_client, ids = client
    headers = {"Authorization": f"Bearer {login(test_client, 'admin')}"}
    prepared = prepare(test_client, headers, ids["high"], "Regenerated")
    first = prepared["enrollment"]["code"]
    regenerated = test_client.post(f"/api/v1/players/{prepared['player']['id']}/enrollment/regenerate", headers=headers)
    assert regenerated.status_code == 200
    second = regenerated.json()["enrollment"]["code"]
    assert first != second
    assert enroll_device(test_client, first).status_code == 404
    assert enroll_device(test_client, second).status_code == 201

    cancelled = prepare(test_client, headers, ids["high"], "Cancelled")
    assert test_client.delete(f"/api/v1/players/{cancelled['player']['id']}/enrollment", headers=headers).status_code == 204
    assert enroll_device(test_client, cancelled["enrollment"]["code"], "cancelled-device").status_code == 404

    original_ttl = routes.settings.enrollment_code_ttl_minutes
    routes.settings.enrollment_code_ttl_minutes = -1
    try:
        expired = prepare(test_client, headers, ids["high"], "Expired")
    finally:
        routes.settings.enrollment_code_ttl_minutes = original_ttl
    assert enroll_device(test_client, expired["enrollment"]["code"], "expired-device").status_code == 410
