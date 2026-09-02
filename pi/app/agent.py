from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import stat
import tempfile
import time
import tomllib
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .platform import PlayerPlatform, platform_for_environment
from .version import PLAYER_VERSION

LOG = logging.getLogger("signal.player")


def atomic_write(path: Path, data: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = path.stat()
    except FileNotFoundError:
        existing = None
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        stream.write(data)
        temp = Path(stream.name)
    os.chmod(temp, stat.S_IMODE(existing.st_mode) if existing else mode)
    if existing:
        try:
            os.chown(temp, existing.st_uid, existing.st_gid)
        except PermissionError:
            # The unprivileged player can still update its own configuration;
            # retain ownership of the replacement in that case.
            pass
    temp.replace(path)


class PlayerAgent:
    def __init__(self, state_dir: str | Path | None = None, api_url: str | None = None, platform: PlayerPlatform | None = None, config_path: str | Path | None = None):
        self.state_dir = Path(state_dir or os.getenv("SIGNAL_STATE_DIR", "/var/lib/signal-player"))
        self.config_path = Path(config_path or os.getenv("SIGNAL_CONFIG_PATH", "/etc/signal-player/config.toml"))
        configured_url = self._configured_server_url(api_url)
        self.server_url, self.api_url = self._normalise_server_url(configured_url)
        self.platform = platform or platform_for_environment()
        self.identity_path = self.state_dir / "identity" / "device.json"
        self.manifest_path = self.state_dir / "manifest" / "active.json"
        self.media_dir = self.state_dir / "cache" / "media"
        self.runtime_path = self.state_dir / "runtime" / "state.json"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.state_dir, 0o700)
        self.identity = self._identity()
        self.runtime = self._read_json(self.runtime_path, {"renderer": "starting", "cache": "empty"})
        if not self.enrolled and self.runtime.get("enrollment_status", "").startswith(("Unable to contact Signal", "getting a new enrollment code")):
            self.runtime["enrollment_status"] = "Ready to connect."
            self._save_runtime()
        self.client = httpx.Client(timeout=15)

    def _configured_server_url(self, explicit_url: str | None) -> str:
        if explicit_url:
            return explicit_url
        try:
            configured = tomllib.loads(self.config_path.read_text()).get("server_url")
            if isinstance(configured, str) and configured:
                return configured
        except (OSError, ValueError, tomllib.TOMLDecodeError):
            pass
        return os.getenv("SIGNAL_SERVER_URL") or os.getenv("SIGNAL_API_URL", "http://api:8000")

    @staticmethod
    def _normalise_server_url(value: str) -> tuple[str, str]:
        server_url = value.strip().rstrip("/")
        parsed = urlparse(server_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Signal server must be an http or https URL with a host.")
        api_url = server_url if server_url.endswith("/api/v1") else f"{server_url}/api/v1"
        return server_url.removesuffix("/api/v1"), api_url

    def _read_json(self, path: Path, default):
        try:
            return json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return default

    def _identity(self) -> dict:
        identity = self._read_json(self.identity_path, None)
        if identity:
            # Safe upgrade path: discard only the old, player-generated short
            # code. Never erase an enrolled device credential or cached media.
            if not self.enrollment_fields_removed(identity):
                identity.pop("enrollment_code", None)
                identity.pop("enrollment_expires_at", None)
                atomic_write(self.identity_path, json.dumps(identity).encode())
            return identity
        identity = {"device_identifier": str(uuid.uuid4())}
        atomic_write(self.identity_path, json.dumps(identity).encode())
        return identity

    @staticmethod
    def enrollment_fields_removed(identity: dict) -> bool:
        return "enrollment_code" not in identity and "enrollment_expires_at" not in identity

    def set_server_url(self, value: str) -> None:
        server_url, api_url = self._normalise_server_url(value)
        atomic_write(self.config_path, f'server_url = "{server_url}"\n'.encode())
        self.server_url, self.api_url = server_url, api_url

    def _save_runtime(self) -> None:
        atomic_write(self.runtime_path, json.dumps(self.runtime).encode())

    @property
    def enrolled(self) -> bool:
        return bool(self.identity.get("player_id") and self.identity.get("device_secret"))

    def headers(self) -> dict:
        return {"X-Signal-Player-ID": self.identity["player_id"], "X-Signal-Player-Secret": self.identity["device_secret"]}

    def active_manifest(self) -> dict | None:
        return self._read_json(self.manifest_path, None)

    def enroll(self, code: str) -> dict:
        """Redeem an administrator-generated one-time code outbound to Signal."""
        if self.enrolled:
            return {"status": "enrolled"}
        self.runtime["enrollment_status"] = "Connecting to Signal…"
        self._save_runtime()
        try:
            response = self.client.post(f"{self.api_url}/device/enroll", json={"code": code.strip().upper(), "device_identifier": self.identity["device_identifier"], "software_version": PLAYER_VERSION, "platform_metadata": self.platform.network_state()})
        except httpx.RequestError:
            self.runtime["enrollment_status"] = "Unable to reach Signal. Check the server address and network connection."
            self._save_runtime()
            return {"status": "unavailable"}
        if response.status_code == 410:
            message = "That enrollment code has expired. Generate a new code in Signal and enter it here."
        elif response.status_code == 409:
            message = "That enrollment code has already been used."
        elif response.status_code in {400, 404, 422}:
            message = "That enrollment code is not valid."
        elif response.status_code == 429:
            message = "Too many attempts. Please wait and try again."
        elif response.status_code >= 400:
            message = "Unable to connect this display right now. Please try again."
        else:
            payload = response.json()
            self.identity.update({"player_id": payload["player_id"], "device_secret": payload["device_secret"]})
            atomic_write(self.identity_path, json.dumps(self.identity).encode())
            self.runtime["enrollment_status"] = "Display connected. Loading signage…"
            self.runtime["credential_failures"] = 0
            self._save_runtime()
            LOG.info("Player enrollment completed")
            return {"status": "enrolled"}
        self.runtime["enrollment_status"] = message
        self._save_runtime()
        return {"status": "error", "message": message}

    def reset_enrollment(self) -> None:
        """Development reset that preserves cache but creates a fresh device ID."""
        self.identity.pop("player_id", None)
        self.identity.pop("device_secret", None)
        self.identity["device_identifier"] = str(uuid.uuid4())
        atomic_write(self.identity_path, json.dumps(self.identity).encode())
        self.runtime["enrollment_status"] = "Device needs re-enrollment."
        self.runtime["credential_failures"] = 0
        self._save_runtime()

    def _download_media(self, manifest: dict) -> None:
        self.media_dir.mkdir(parents=True, exist_ok=True)
        for asset in manifest.get("media", []):
            asset_id = asset["assetId"]
            target = self.media_dir / asset_id
            if target.is_file() and self._sha256(target) == asset["sha256"]:
                continue
            path = asset["path"]
            # Manifest paths may be API-relative or already include /api/v1.
            # Build one canonical URL rather than accidentally producing
            # /api/v1/api/v1/... and aborting the heartbeat cycle on a 404.
            base = self.server_url if path.startswith("/api/v1/") else self.api_url
            response = self.client.get(f"{base}{path}", headers=self.headers())
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
        payload = {"software_version": PLAYER_VERSION, "applied_state_revision": manifest.get("revision"), "renderer_status": renderer, "cache_state": self.runtime.get("cache", "empty"), "resolution": self.platform.resolution(), "uptime_seconds": int(time.monotonic()), "disk_usage": self.platform.disk_usage(str(self.state_dir)), "network_state": self.platform.network_state(), "temperature": self.platform.temperature()}
        self.client.post(f"{self.api_url}/player-agent/heartbeat", headers=self.headers(), json=payload).raise_for_status()

    def commands(self) -> None:
        if not self.enrolled:
            return
        for command in self.client.get(f"{self.api_url}/player-agent/commands", headers=self.headers()).json():
            status, result = "completed", {}
            try:
                if command["command"] == "force_sync":
                    changed = self.sync()
                    result = {"state": "synced" if changed else "already_up_to_date"}
                elif command["command"] == "restart_renderer": status, result = self.platform.restart_renderer()
                elif command["command"] == "clear_cache": shutil.rmtree(self.media_dir, ignore_errors=True); status, result = "completed", {"cache": "cleared"}
                elif command["command"] == "set_resolution": status, result = self.platform.set_resolution((command.get("payload") or {}).get("resolution", ""))
                else: status, result = "unsupported", {"reason": "not supported by this platform"}
            except Exception as exc:  # retain active manifest when commands fail
                status, result = "failed", {"error": str(exc)}
            self.client.post(f"{self.api_url}/player-agent/commands/{command['id']}/result", headers=self.headers(), json={"status": status, "result": result}).raise_for_status()

    def cycle(self, *, sync_state: bool = True) -> None:
        try:
            if sync_state:
                self.sync()
                self.heartbeat()
            self.commands()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403} and self.enrolled:
                failures = int(self.runtime.get("credential_failures", 0)) + 1
                self.runtime["credential_failures"] = failures
                if failures >= 3:
                    self.reset_enrollment()
                else:
                    self._save_runtime()
            LOG.warning("Signal rejected a player request; continuing cached playback: %s", exc)
        except Exception as exc:
            LOG.warning("Server sync unavailable; continuing cached playback: %s", exc)


if __name__ == "__main__":
    import sys

    if sys.argv[1:] == ["reset-enrollment"]:
        PlayerAgent().reset_enrollment()
        print("Enrollment credentials reset; cached signage was preserved.")
    else:
        raise SystemExit("Usage: python -m app.agent reset-enrollment")
