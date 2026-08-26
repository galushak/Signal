"""The only module which knows about Docker or Raspberry Pi host details."""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class PlatformStatus:
    temperature: str | float
    renderer_status: str


class PlayerPlatform:
    def disk_usage(self, state_dir: str) -> dict:
        usage = shutil.disk_usage(state_dir)
        return {"total": usage.total, "used": usage.used, "free": usage.free}

    def network_state(self) -> dict:
        return {"online": True, "kind": "container"}

    def temperature(self) -> str | float:
        return "unsupported"

    def renderer_status(self) -> str:
        return "local_web_only"

    def restart_renderer(self) -> tuple[str, dict]:
        return "unsupported", {"reason": "renderer restart is not available on this platform"}

    def restart_player(self) -> tuple[str, dict]:
        return "unsupported", {"reason": "container restarts are managed by Docker"}


class DockerSimulatorPlatform(PlayerPlatform):
    def __init__(self):
        self.renderer: subprocess.Popen | None = None

    def start_renderer(self, url: str) -> None:
        if os.getenv("SIGNAL_START_CHROMIUM", "true").lower() != "true" or self.renderer and self.renderer.poll() is None:
            return
        self.renderer = subprocess.Popen(["chromium", "--headless", "--no-sandbox", "--disable-gpu", "--autoplay-policy=no-user-gesture-required", "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=9222", "--disable-dev-shm-usage", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def renderer_status(self) -> str:
        return "running" if self.renderer and self.renderer.poll() is None else "not_running"

    def restart_renderer(self) -> tuple[str, dict]:
        if self.renderer and self.renderer.poll() is None:
            self.renderer.terminate()
        self.renderer = None
        self.start_renderer("http://127.0.0.1:8090/player")
        return "completed", {"renderer": self.renderer_status()}


class RaspberryPiPlatform(PlayerPlatform):
    """Production adapter; units launch Chromium in kiosk mode on Pi OS."""
    def temperature(self) -> str | float:
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", encoding="utf-8") as stream:
                return int(stream.read().strip()) / 1000
        except (OSError, ValueError):
            return "unsupported"

    def network_state(self) -> dict:
        return {"online": "unknown", "kind": "raspberry-pi"}

    def renderer_status(self) -> str:
        try:
            result = subprocess.run(["pgrep", "-u", "signal-player", "-f", "chromium"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            return "running" if result.returncode == 0 else "not_running"
        except OSError:
            return "unknown"


def platform_for_environment() -> PlayerPlatform:
    return RaspberryPiPlatform() if os.getenv("SIGNAL_PLATFORM") == "raspberry-pi" else DockerSimulatorPlatform()
