from test_functional_core import client, login


def test_enrollment_is_single_use_and_device_manifest_is_etagged(client):
    test_client, ids = client
    headers = {"Authorization": f"Bearer {login(test_client, 'admin')}"}
    code = "ABC-234"
    assert test_client.post("/api/v1/player-agent/enrollment/start", json={"code": code, "device_identifier": "test-device-0001"}).status_code == 200
    claim = test_client.post("/api/v1/players/enroll", headers=headers, json={"code": code, "name": "TEST PI", "building_id": ids["high"]})
    assert claim.status_code == 201
    assert test_client.post("/api/v1/players/enroll", headers=headers, json={"code": code, "name": "duplicate", "building_id": ids["high"]}).status_code == 409
    credentials = test_client.get(f"/api/v1/player-agent/enrollment/{code}").json()
    assert credentials["status"] == "enrolled"
    device_headers = {"X-Signal-Player-ID": credentials["player_id"], "X-Signal-Player-Secret": credentials["device_secret"]}
    heartbeat = test_client.post("/api/v1/player-agent/heartbeat", headers=device_headers, json={"software_version": "0.1.0", "renderer_status": "running", "cache_state": "ready", "temperature": "unsupported"})
    assert heartbeat.status_code == 200
    manifest = test_client.get("/api/v1/player-agent/manifest", headers=device_headers)
    assert manifest.status_code == 200
    assert manifest.json()["schemaVersion"] == 1
    assert test_client.get("/api/v1/player-agent/manifest", headers={**device_headers, "If-None-Match": manifest.headers["etag"]}).status_code == 304
    assert test_client.get("/api/v1/player-agent/manifest", headers={"X-Signal-Player-ID": credentials["player_id"], "X-Signal-Player-Secret": "wrong"}).status_code == 401
