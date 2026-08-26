from base64 import b64decode

from test_functional_core import client, login


def document(asset_id: str | None = None) -> dict:
    element = {"id": "title", "type": "text", "text": "Trash test", "x": 100, "y": 100, "width": 800, "height": 100}
    if asset_id:
        element = {"id": "image", "type": "image", "assetId": asset_id, "x": 100, "y": 100, "width": 800, "height": 500}
    return {"schema": "signal.design/v1", "canvas": {"width": 1920, "height": 1080}, "elements": [element]}


def test_default_display_mode_and_manifest_mode(client):
    test_client, ids = client
    headers = {"Authorization": f"Bearer {login(test_client, 'admin')}"}
    design = test_client.post("/api/v1/content", headers=headers, json={"name": "Fit mode", "design_document": document()}).json()
    assert test_client.post(f"/api/v1/content/{design['id']}/publish", headers=headers).status_code == 200
    assignment = test_client.post(f"/api/v1/content/{design['id']}/assignments", headers=headers, json={"destination_type": "player", "destination_id": ids["cafeteria"]})
    assert assignment.status_code == 201
    assert assignment.json()["display_mode"] == "fit"
    changed = test_client.patch(f"/api/v1/assignments/{assignment.json()['id']}", headers=headers, json={"destination_type": "player", "destination_id": ids["cafeteria"], "display_mode": "fill"})
    assert changed.status_code == 200
    assert changed.json()["display_mode"] == "fill"


def test_design_trash_removes_assignments_then_restores(client):
    test_client, ids = client
    headers = {"Authorization": f"Bearer {login(test_client, 'admin')}"}
    design = test_client.post("/api/v1/content", headers=headers, json={"name": "Trash design", "design_document": document()}).json()
    assert test_client.post(f"/api/v1/content/{design['id']}/publish", headers=headers).status_code == 200
    assert test_client.post(f"/api/v1/content/{design['id']}/assignments", headers=headers, json={"destination_type": "player", "destination_id": ids["cafeteria"]}).status_code == 201
    assert test_client.post(f"/api/v1/content/{design['id']}/trash", headers=headers, json={}).status_code == 409
    trashed = test_client.post(f"/api/v1/content/{design['id']}/trash", headers=headers, json={"remove_assignments": True})
    assert trashed.status_code == 200 and trashed.json()["assignments_removed"] == 1
    assert design["id"] not in {item["id"] for item in test_client.get("/api/v1/library?kind=all", headers=headers).json()}
    assert design["id"] in {item["id"] for item in test_client.get("/api/v1/library?kind=trash", headers=headers).json()}
    assert test_client.post(f"/api/v1/content/{design['id']}/untrash", headers=headers).status_code == 200
    assert design["id"] in {item["id"] for item in test_client.get("/api/v1/library?kind=design", headers=headers).json()}


def test_media_referenced_by_design_cannot_be_trashed(client):
    test_client, _ = client
    headers = {"Authorization": f"Bearer {login(test_client, 'admin')}"}
    png = b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLqNwAAAABJRU5ErkJggg==")
    asset = test_client.post("/api/v1/media/upload", headers=headers, data={"scope_type": "district"}, files=[("files", ("protected.png", png, "image/png"))]).json()[0]
    assert test_client.post("/api/v1/content", headers=headers, json={"name": "Uses protected image", "design_document": document(asset["id"])}).status_code == 201
    blocked = test_client.post(f"/api/v1/media/{asset['id']}/trash", headers=headers, json={})
    assert blocked.status_code == 409
    assert "used by 1 Design" in blocked.json()["detail"]
