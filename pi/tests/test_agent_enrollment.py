from datetime import UTC, datetime, timedelta

from app.agent import PlayerAgent
from app.platform import PlayerPlatform


class Reply:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload

    def raise_for_status(self):
        return None


class EnrollmentClient:
    def __init__(self, status="pending"):
        self.status = status
        self.codes = []

    def post(self, url, json, **_):
        if url.endswith("/start"):
            self.codes.append(json["code"])
            return Reply({"expires_at": (datetime.now(UTC) + timedelta(minutes=15)).isoformat()})
        return Reply({"ok": True})

    def get(self, url, **_):
        if self.status == "enrolled":
            return Reply({"status": "enrolled", "player_id": "player-1", "device_secret": "secret"})
        return Reply({"status": "pending"})


def test_pending_code_is_stable_then_renews_and_stops_after_claim(tmp_path):
    agent = PlayerAgent(state_dir=tmp_path, api_url="http://signal", platform=PlayerPlatform())
    fake = EnrollmentClient()
    agent.client = fake
    agent.enroll()
    original = agent.identity["enrollment_code"]
    agent.enroll()
    assert agent.identity["enrollment_code"] == original
    agent.identity["enrollment_expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    agent.enroll()
    renewed = agent.identity["enrollment_code"]
    assert renewed != original
    assert fake.codes[-1] == renewed
    fake.status = "enrolled"
    agent.enroll()
    assert agent.enrolled
    assert agent.renew_enrollment()["status"] == "enrolled"
    assert "enrollment_code" not in agent.identity
