from app.agent import PlayerAgent
from app.platform import PlayerPlatform


class Reply:
    status_code = 201

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class EnrollmentClient:
    def __init__(self):
        self.requests = []

    def post(self, url, json, **_):
        self.requests.append((url, json))
        return Reply({"player_id": "player-1", "device_secret": "secret"})


def test_server_generated_code_enrolls_and_identity_survives_restart(tmp_path):
    config_path = tmp_path / "etc" / "config.toml"
    agent = PlayerAgent(state_dir=tmp_path / "state", api_url="http://signal", platform=PlayerPlatform(), config_path=config_path)
    fake = EnrollmentClient()
    agent.client = fake
    assert agent.enroll("ABC-234")["status"] == "enrolled"
    assert fake.requests[0][0].endswith("/api/v1/device/enroll")
    assert fake.requests[0][1]["code"] == "ABC-234"
    restarted = PlayerAgent(state_dir=tmp_path / "state", api_url="http://signal", platform=PlayerPlatform(), config_path=config_path)
    assert restarted.enrolled
    assert "enrollment_code" not in restarted.identity
    restarted.reset_enrollment()
    assert not restarted.enrolled
    assert restarted.identity["device_identifier"]


def test_server_address_is_validated_and_persisted(tmp_path):
    config_path = tmp_path / "etc" / "config.toml"
    agent = PlayerAgent(state_dir=tmp_path / "state", api_url="http://signal", platform=PlayerPlatform(), config_path=config_path)
    agent.set_server_url("https://signal.example.org")
    restarted = PlayerAgent(state_dir=tmp_path / "state", platform=PlayerPlatform(), config_path=config_path)
    assert restarted.server_url == "https://signal.example.org"
    assert restarted.api_url == "https://signal.example.org/api/v1"
