from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import shutil
import tempfile
import time
import uuid
from pathlib import Path

import httpx

from .platform import PlayerPlatform, platform_for_environment

LOG = logging.getLogger("signal.player")
PLAYER_VERSION = "0.1.0"


def atomic_write(path: Path, data: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        stream.write(data)
        temp = Path(stream.name)
    os.chmod(temp, mode)
    temp.replace(path)


class PlayerAgent:
    def __init__(self, state_dir: str | Path | None = None, api_url: str | None = None, platform: PlayerPlatform | None = None):
        self.state_dir = Path(state_dir or os.getenv("SIGNAL_STATE_DIR", "/var/lib/signal-player"))
        self.api_url = (api_url or os.getenv("SIGNAL_API_URL", "http://api:8000/api/v1")).rstrip("/")
        self.platform = platform or platform_for_environment()
        self.identity_path = self.state_dir / "identity" / "device.json"
        self.manifest_path = self.state_dir / "manifest" / "active.json"
        self.media_dir = self.state_dir / "cache" / "media"
        self.runtime_path = self.state_dir / "runtime" / "state.json"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.state_dir, 0o700)
        self.identity = self._identity()
        self.runtime = self._read_json(self.runtime_path, {"renderer": "starting", "cache": "empty"})
        self.client = httpx.Client(timeout=15)

    @staticmethod
    def enrollment_code() -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        return "".join(secrets.choice(alphabet) for _ in range(6))[:3] + "-" + "".join(secrets.choice(alphabet) for _ in range(6))[3:]

    def _read_json(self, path: Path, default):
        try:
            return json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return default

    def _identity(self) -> dict:
        identity = self._read_json(self.identity_path, None)
        if identity:
            return identity
        identity = {"device_identifier": str(uuid.uuid4()), "enrollment_code": self.enrollment_code()}
        atomic_write(self.identity_path, json.dumps(identity).encode())
        return identity

    def _save_runtime(self) -> None:
        atomic_write(self.runtime_path, json.dumps(self.runtime).encode())

    @property
    def enrolled(self) -> bool:
        return bool(self.identity.get("player_id") and self.identity.get("device_secret"))

    def headers(self) -> dict:
        return {"X-Signal-Player-ID": self.identity["player_id"], "X-Signal-Player-Secret": self.identity["device_secret"]}

    def active_manifest(self) -> dict | None:
        return self._read_json(self.manifest_path, None)

    def enroll(self) -> None:
        if self.enrolled:
            return
        code = self.identity["enrollment_code"]
        response = self.client.post(f"{self.api_url}/player-agent/enrollment/start", json={"code": code, "device_identifier": self.identity["device_identifier"]})
        response.raise_for_status()
        status = self.client.get(f"{self.api_url}/player-agent/enrollment/{code}")
        status.raise_for_status()
        payload = status.json()
        if payload.get("status") == "enrolled":
            self.identity.update({"player_id": payload["player_id"], "device_secret": payload["device_secret"]})
            self.identity.pop("enrollment_code", None)
            atomic_write(self.identity_path, json.dumps(self.identity).encode())
            LOG.info("Player enrollment completed")

    def _download_media(self, manifest: dict) -> None:
        self.media_dir.mkdir(parents=True, exist_ok=True)
        for asset in manifest.get("media", []):
            asset_id = asset["assetId"]
            target = self.media_dir / asset_id
            if target.is_file() and self._sha256(target) == asset["sha256"]:
                continue
            response = self.client.get(f"{self.api_url}{asset['path']}", headers=self.headers())
            response.raise_for_status()
            digest = hashlib.sha256(response.content).hexdigest()
            if digest != asset["sha256"]:
                raise ValueError(f"Checksum mismatch for {asset_id}")
            atomic_write(target, response.content, 0o600)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1_048_576), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def sync(self) -> bool:
        if not self.enrolled:
            self.enroll()
            return False
        previous = self.active_manifest()
        headers = self.headers()
        if previous and previous.get("revision"):
            headers["If-None-Match"] = f'"{previous["revision"]}"'
        response = self.client.get(f"{self.api_url}/player-agent/manifest", headers=headers)
        if response.status_code == 304:
            return False
        response.raise_for_status()
        manifest = response.json()
        if manifest.get("schemaVersion") != 1 or not manifest.get("revision"):
            raise ValueError("Unsupported or malformed player manifest")
        # Downloads complete and validate before this one atomic manifest switch.
        self._download_media(manifest)
        atomic_write(self.manifest_path, json.dumps(manifest).encode())
        self.runtime["cache"] = "ready"
        self.runtime["applied_revision"] = manifest["revision"]
        self._save_runtime()
        LOG.info("Applied desired state %s", manifest["revision"][:12])
        return True

    def heartbeat(self) -> None:
        if not self.enrolled:
            return
        manifest = self.active_manifest() or {}
        renderer = getattr(self.platform, "renderer_status", lambda: "local_web_only")()
        self.runtime["renderer"] = renderer
        self._save_runtime()
        payload = {"software_version": PLAYER_VERSION, "applied_state_revision": manifest.get("revision"), "renderer_status": renderer, "cache_state": self.runtime.get("cache", "empty"), "resolution": "1920x1080", "uptime_seconds": int(time.monotonic()), "disk_usage": self.platform.disk_usage(str(self.state_dir)), "network_state": self.platform.network_state(), "temperature": self.platform.temperature()}
        self.client.post(f"{self.api_url}/player-agent/heartbeat", headers=self.headers(), json=payload).raise_for_status()

    def commands(self) -> None:
        if not self.enrolled:
            return
        for command in self.client.get(f"{self.api_url}/player-agent/commands", headers=self.headers()).json():
            status, result = "completed", {}
            try:
                if command["command"] == "force_sync": self.sync()
                elif command["command"] == "restart_renderer": status, result = self.platform.restart_renderer()
                elif command["command"] == "clear_cache": shutil.rmtree(self.media_dir, ignore_errors=True); status, result = "completed", {"cache": "cleared"}
                else: status, result = "unsupported", {"reason": "not supported by this platform"}
            except Exception as exc:  # retain active manifest when commands fail
                status, result = "failed", {"error": str(exc)}
            self.client.post(f"{self.api_url}/player-agent/commands/{command['id']}/result", headers=self.headers(), json={"status": status, "result": result}).raise_for_status()

    def cycle(self) -> None:
        try:
            self.sync()
            self.heartbeat()
            self.commands()
        except Exception as exc:
            LOG.warning("Server sync unavailable; continuing cached playback: %s", exc)
