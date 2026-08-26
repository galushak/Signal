from test_functional_core import client, login


def document(text: str) -> dict:
    return {"schema": "signal.design/v1", "canvas": {"width": 1920, "height": 1080}, "elements": [{"id": "headline", "type": "text", "text": text, "x": 120, "y": 120, "width": 900, "height": 120}]}


def test_layout_zone_content_publish_assignment_and_preview(client):
    test_client, ids = client
    token = login(test_client, "admin")
    headers = {"Authorization": f"Bearer {token}"}
    layout = test_client.post("/api/v1/layouts", headers=headers, json={"name": "Cafeteria Test", "enabled": True}).json()
    zone = test_client.post(f"/api/v1/layouts/{layout['id']}/zones", headers=headers, json={"name": "Menu", "x": 0, "y": 0, "width": 1200, "height": 1080}).json()
    player = test_client.patch(f"/api/v1/players/{ids['cafeteria']}", headers=headers, json={"name": "HS Cafeteria", "building_id": ids["high"], "enabled": True, "layout_id": layout["id"]})
    assert player.status_code == 200
    created = test_client.post("/api/v1/content", headers=headers, json={"name": "Lunch", "scope_type": "zone", "scope_id": zone["id"], "design_document": document("Monday lunch")})
    assert created.status_code == 201
    content = created.json()
    published = test_client.post(f"/api/v1/content/{content['id']}/publish", headers=headers)
    assert published.status_code == 200
    assignment = test_client.post(f"/api/v1/content/{content['id']}/assignments", headers=headers, json={"destination_type": "zone", "destination_id": zone["id"], "priority": 2, "transition": "fade"})
    assert assignment.status_code == 201
    preview = test_client.get(f"/api/v1/players/{ids['cafeteria']}/preview", headers=headers).json()
    assert preview["kind"] == "server_desired_state"
    assert preview["eligible_assignments"][0]["content"]["name"] == "Lunch"


def test_player_layout_change_and_custom_layout_deletion_return_to_full_screen(client):
    test_client, ids = client
    headers = {"Authorization": f"Bearer {login(test_client, 'admin')}"}
    layouts = test_client.get("/api/v1/layouts", headers=headers).json()
    full_screen = next(item for item in layouts if item["system"])
    assert full_screen["name"] == "Full Screen"
    assert full_screen["zones"][0]["name"] == "Main"
    assert test_client.delete(f"/api/v1/layouts/{full_screen['id']}", headers=headers).status_code == 409

    custom = test_client.post("/api/v1/layouts", headers=headers, json={"name": "Lobby Test", "enabled": True}).json()
    changed = test_client.patch(f"/api/v1/players/{ids['cafeteria']}/layout", headers=headers, json={"layout_id": custom["id"]})
    assert changed.status_code == 200
    assert changed.json()["player"]["effective_layout"]["id"] == custom["id"]
    assert changed.json()["player"]["desired_state_revision"]
    assert test_client.patch(f"/api/v1/players/{ids['cafeteria']}/layout", headers={"Authorization": f"Bearer {login(test_client, 'kitchen')}"}, json={"layout_id": full_screen["id"]}).status_code == 403

    removed = test_client.delete(f"/api/v1/layouts/{custom['id']}", headers=headers)
    assert removed.status_code == 200
    assert removed.json()["players_returned_to_full_screen"] == 1
    player = next(item for item in test_client.get("/api/v1/players", headers=headers).json() if item["id"] == ids["cafeteria"])
    assert player["layout_id"] is None
    assert player["effective_layout"]["id"] == full_screen["id"]
    actions = {event["action"] for event in test_client.get("/api/v1/audit", headers=headers).json()}
    assert {"player.layout_changed", "layout.deleted"}.issubset(actions)


def test_published_versions_are_immutable_and_restore_creates_draft(client):
    test_client, _ = client
    token = login(test_client, "admin")
    headers = {"Authorization": f"Bearer {token}"}
    content = test_client.post("/api/v1/content", headers=headers, json={"name": "Versioned", "design_document": document("first")}).json()
    assert test_client.post(f"/api/v1/content/{content['id']}/publish", headers=headers).status_code == 200
    assert test_client.post(f"/api/v1/content/{content['id']}/draft", headers=headers, json={"design_document": document("second")}).status_code == 200
    versions = test_client.get(f"/api/v1/content/{content['id']}/versions", headers=headers).json()
    published = next(version for version in versions if version["state"] == "published")
    assert published["design_document"]["elements"][0]["text"] == "first"
    assert test_client.post(f"/api/v1/content/{content['id']}/publish", headers=headers).status_code == 200
    assert test_client.post(f"/api/v1/content/{content['id']}/restore/{published['revision']}", headers=headers).status_code == 200


def test_zone_only_user_cannot_access_sibling_zone(client):
    test_client, _ = client
    admin = login(test_client, "admin")
    headers = {"Authorization": f"Bearer {admin}"}
    layout = test_client.post("/api/v1/layouts", headers=headers, json={"name": "Zone ACL Test"}).json()
    menu = test_client.post(f"/api/v1/layouts/{layout['id']}/zones", headers=headers, json={"name": "Menu", "x": 0, "y": 0, "width": 960, "height": 1080}).json()
    district = test_client.post(f"/api/v1/layouts/{layout['id']}/zones", headers=headers, json={"name": "District", "x": 960, "y": 0, "width": 960, "height": 1080}).json()
    kitchen = next(item for item in test_client.get("/api/v1/users", headers=headers).json() if item["username"] == "kitchen")
    for capability in ("view", "create_content", "edit_content", "publish", "schedule"):
        assert test_client.post(f"/api/v1/users/{kitchen['id']}/grants", headers=headers, json={"capability": capability, "scope_type": "zone", "scope_id": menu["id"]}).status_code == 201
    kitchen_headers = {"Authorization": f"Bearer {login(test_client, 'kitchen')}"}
    destinations = test_client.get("/api/v1/destinations", headers=kitchen_headers).json()
    assert [zone["id"] for zone in destinations["zones"]] == [menu["id"]]
    content = test_client.post("/api/v1/content", headers=kitchen_headers, json={"name": "Menu only", "scope_type": "zone", "scope_id": menu["id"], "design_document": document("Lunch")})
    assert content.status_code == 201
    assert test_client.post(f"/api/v1/content/{content.json()['id']}/assignments", headers=kitchen_headers, json={"destination_type": "zone", "destination_id": district["id"]}).status_code == 403


def test_unified_library_surfaces_authorized_designs_with_thumbnail(client):
    test_client, _ = client
    headers = {"Authorization": f"Bearer {login(test_client, 'admin')}"}
    content = test_client.post("/api/v1/content", headers=headers, json={"name": "Library Welcome", "design_document": document("WELCOME BACK")}).json()
    library = test_client.get("/api/v1/library?kind=design", headers=headers)
    assert library.status_code == 200
    item = next(item for item in library.json() if item["id"] == content["id"])
    assert item["kind"] == "design"
    thumbnail = test_client.get(item["thumbnail_url"], headers=headers)
    assert thumbnail.status_code == 200
    assert thumbnail.headers["content-type"].startswith("image/svg+xml")
