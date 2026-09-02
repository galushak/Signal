"""The only module which knows about Docker or Raspberry Pi host details."""
from __future__ import annotations

import os
import re
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

    def resolution(self) -> str:
        return "1920x1080"

    def set_resolution(self, resolution: str) -> tuple[str, dict]:
        return "unsupported", {"reason": "display resolution is not available on this platform"}

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
            result = subprocess.run(["pgrep", "-f", "chromium.*127.0.0.1:8090/player"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            return "running" if result.returncode == 0 else "not_running"
        except OSError:
            return "unknown"

    def _xrandr(self, *args: str) -> subprocess.CompletedProcess[str]:
        environment = {**os.environ, "DISPLAY": ":0", "XAUTHORITY": "/var/lib/signal-player/.Xauthority"}
        return subprocess.run(["xrandr", *args], env=environment, text=True, capture_output=True, check=False)

    def resolution(self) -> str:
        try:
            result = self._xrandr("--current")
            match = re.search(r"\s(\d{3,5})x(\d{3,5})\+\d+\+\d+", result.stdout)
            return f"{match.group(1)}x{match.group(2)}" if match else super().resolution()
        except OSError:
            return super().resolution()

    def set_resolution(self, resolution: str) -> tuple[str, dict]:
        if not re.fullmatch(r"\d{3,5}x\d{3,5}", resolution):
            return "failed", {"error": "Invalid resolution."}
        try:
            result = self._xrandr("--size", resolution)
        except OSError as exc:
            return "failed", {"error": str(exc)}
        if result.returncode:
            return "failed", {"error": (result.stderr or result.stdout or "xrandr rejected this resolution.").strip()}
        return "completed", {"resolution": self.resolution()}


def platform_for_environment() -> PlayerPlatform:
    return RaspberryPiPlatform() if os.getenv("SIGNAL_PLATFORM") == "raspberry-pi" else DockerSimulatorPlatform()
