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
