from app.agent import PlayerAgent
from app.cli import main as cli_main
from app.main import PLAYER_HTML
from app.platform import PlayerPlatform, RaspberryPiPlatform
from app.version import PLAYER_VERSION


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


def test_player_renderer_does_not_replace_the_dom_for_the_same_item():
    """Polling may call draw repeatedly, but unchanged playback must be inert."""
    assert "if(renderedKey===key)return" in PLAYER_HTML
    assert "let renderedKey=''" in PLAYER_HTML


def test_direct_media_frame_maps_fit_and_fill_without_grid_sizing():
    assert "function mediaFrame(type,id,displayMode)" in PLAYER_HTML
    assert "displayMode==='fill'?'cover':'contain'" in PLAYER_HTML
    assert "object-position:center center" in PLAYER_HTML
    media_frame = PLAYER_HTML.split("function mediaFrame", 1)[1].split("function playable", 1)[0]
    assert "display:grid;place-items:center" not in media_frame


def test_player_version_is_explicit_and_used_by_cli(capsys):
    assert PLAYER_VERSION == "0.1.0-rc5"
    assert cli_main(["version"]) == 0
    assert capsys.readouterr().out.strip() == PLAYER_VERSION


def test_cli_reset_enrollment_preserves_cached_media(tmp_path, monkeypatch):
    config_path = tmp_path / "etc" / "config.toml"
    state_path = tmp_path / "state"
    monkeypatch.setenv("SIGNAL_STATE_DIR", str(state_path))
    monkeypatch.setenv("SIGNAL_CONFIG_PATH", str(config_path))
    agent = PlayerAgent(state_dir=state_path, api_url="http://signal", platform=PlayerPlatform(), config_path=config_path)
    agent.identity.update({"player_id": "player-1", "device_secret": "secret"})
    agent._identity()
    agent.media_dir.mkdir(parents=True)
    (agent.media_dir / "asset").write_bytes(b"cached")
    cli_main(["reset-enrollment"])
    assert (agent.media_dir / "asset").exists()
    assert not PlayerAgent(state_dir=state_path, api_url="http://signal", platform=PlayerPlatform(), config_path=config_path).enrolled


def test_raspberry_pi_platform_reports_unavailable_renderer_without_faking_it(monkeypatch):
    monkeypatch.setattr("app.platform.subprocess.run", lambda *_, **__: type("Result", (), {"returncode": 1})())
    assert RaspberryPiPlatform().renderer_status() == "not_running"
