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


def test_full_screen_fallback_is_exposed_and_maps_direct_content_to_main(client):
    test_client, ids = client
    headers = {"Authorization": f"Bearer {login(test_client, 'admin')}"}

    # Existing null-layout records are readable as Full Screen before any admin
    # needs to repair them, and new enrollments store that usable default.
    existing = next(item for item in test_client.get("/api/v1/players", headers=headers).json() if item["id"] == ids["cafeteria"])
    assert existing["layout_id"] is None
    assert existing["effective_layout"]["name"] == "Full Screen"
    prepared = prepare(test_client, headers, ids["high"], "Fallback PI")
    assert prepared["player"]["effective_layout"] == {"id": "00000000-0000-4000-8000-000000000001", "name": "Full Screen", "system": True}

    credentials = enroll_device(test_client, prepared["enrollment"]["code"], "fallback-device-0001").json()
    content = test_client.post("/api/v1/content", headers=headers, json={
        "name": "Direct fallback content",
        "design_document": {"schema": "signal.design/v1", "canvas": {"width": 1920, "height": 1080}, "elements": []},
    }).json()
    assert test_client.post(f"/api/v1/content/{content['id']}/publish", headers=headers).status_code == 200
    assert test_client.post(f"/api/v1/content/{content['id']}/assignments", headers=headers, json={
        "destination_type": "player", "destination_id": prepared["player"]["id"],
    }).status_code == 201
    manifest = test_client.get("/api/v1/player-agent/manifest", headers={
        "X-Signal-Player-ID": credentials["player_id"], "X-Signal-Player-Secret": credentials["device_secret"],
    })
    assert manifest.status_code == 200
    payload = manifest.json()
    assert payload["layout"]["name"] == "Full Screen"
    assert payload["layout"]["zones"] == [
        {"id": "00000000-0000-4000-8000-000000000002", "name": "Main", "x": 0, "y": 0, "width": 1920, "height": 1080, "zIndex": 0, "background": None, "border": None, "padding": 0}
    ]
    assert payload["content"][0]["assignment"]["destinationType"] == "zone"
    assert payload["content"][0]["assignment"]["destinationId"] == "00000000-0000-4000-8000-000000000002"


def test_sending_multiple_designs_appends_independent_player_assignments(client):
    test_client, ids = client
    headers = {"Authorization": f"Bearer {login(test_client, 'admin')}"}
    player = prepare(test_client, headers, ids["high"], "Append test display")["player"]
    document = {"schema": "signal.design/v1", "canvas": {"width": 1920, "height": 1080}, "elements": []}
    assignment_ids = []
    for name in ("Design A", "Design B", "Design C"):
        design = test_client.post("/api/v1/content", headers=headers, json={"name": name, "design_document": document}).json()
        assert test_client.post(f"/api/v1/content/{design['id']}/publish", headers=headers).status_code == 200
        assigned = test_client.post(f"/api/v1/content/{design['id']}/assignments", headers=headers, json={"destination_type": "player", "destination_id": player["id"], "transition": "none"})
        assert assigned.status_code == 201
        assignment_ids.append(assigned.json()["id"])
    details = test_client.get(f"/api/v1/players/{player['id']}", headers=headers).json()
    assert [item["id"] for item in details["assignments"]] == assignment_ids
    assert test_client.delete(f"/api/v1/assignments/{assignment_ids[1]}", headers=headers).status_code == 200
    remaining = test_client.get(f"/api/v1/players/{player['id']}", headers=headers).json()["assignments"]
    assert [item["id"] for item in remaining] == [assignment_ids[0], assignment_ids[2]]


def test_force_sync_reports_player_acknowledgement(client):
    test_client, ids = client
    headers = {"Authorization": f"Bearer {login(test_client, 'admin')}"}
    prepared = prepare(test_client, headers, ids["high"], "Sync acknowledgement")
    credentials = enroll_device(test_client, prepared["enrollment"]["code"], "sync-device-0001").json()
    player_id = prepared["player"]["id"]
    device_headers = {"X-Signal-Player-ID": credentials["player_id"], "X-Signal-Player-Secret": credentials["device_secret"]}
    queued = test_client.post(f"/api/v1/players/{player_id}/commands", headers=headers, json={"command": "force_sync"})
    assert queued.status_code == 201
    command_id = queued.json()["id"]
    assert test_client.get(f"/api/v1/players/{player_id}/commands/{command_id}", headers=headers).json()["status"] == "queued"
    assert test_client.get("/api/v1/player-agent/commands", headers=device_headers).json() == [{"id": command_id, "command": "force_sync"}]
    assert test_client.post(f"/api/v1/player-agent/commands/{command_id}/result", headers=device_headers, json={"status": "completed", "result": {"state": "already_up_to_date"}}).status_code == 200
    status = test_client.get(f"/api/v1/players/{player_id}/commands/{command_id}", headers=headers).json()
    assert status["status"] == "completed"
    assert status["result"] == {"state": "already_up_to_date"}


def test_web_links_and_resolution_commands_are_player_ready(client):
    test_client, ids = client
    headers = {"Authorization": f"Bearer {login(test_client, 'admin')}"}
    link = test_client.post(
        "/api/v1/content/web-link",
        headers=headers,
        json={"name": "Board Slides", "url": "https://docs.google.com/presentation/d/example/embed"},
    )
    assert link.status_code == 201
    library = test_client.get("/api/v1/library?kind=web", headers=headers).json()
    assert any(item["id"] == link.json()["id"] and item["status"] == "Published" for item in library)

    prepared = prepare(test_client, headers, ids["high"], "Resolution test")
    credentials = enroll_device(test_client, prepared["enrollment"]["code"], "resolution-device-0001").json()
    player_id = prepared["player"]["id"]
    device_headers = {"X-Signal-Player-ID": credentials["player_id"], "X-Signal-Player-Secret": credentials["device_secret"]}
    assert test_client.post("/api/v1/player-agent/heartbeat", headers=device_headers, json={"resolution": "1280x720"}).status_code == 200
    player = test_client.get(f"/api/v1/players/{player_id}", headers=headers).json()["player"]
    assert player["resolution"] == "1280x720"
    assert player["connected_ip"]

    queued = test_client.post(f"/api/v1/players/{player_id}/commands", headers=headers, json={"command": "set_resolution", "resolution": "1920x1080"})
    assert queued.status_code == 201
    command = test_client.get("/api/v1/player-agent/commands", headers=device_headers).json()[0]
    assert command["command"] == "set_resolution"
    assert command["payload"] == {"resolution": "1920x1080"}
