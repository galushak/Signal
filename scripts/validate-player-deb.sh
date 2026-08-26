#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
artifact=${1:-"$root/dist/$(ls "$root"/dist/signal-player_*_arm64.deb 2>/dev/null | xargs -r -n1 basename | head -n1)"}
if [[ ! -f "$artifact" ]]; then
  echo "Usage: $0 /absolute/path/to/signal-player_*_arm64.deb" >&2
  exit 1
fi

docker run --rm --platform linux/arm64 -v "$artifact:/tmp/signal-player.deb:ro" debian:bookworm-slim sh -ceu '
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends /tmp/signal-player.deb
  /usr/bin/signal-player version
  cd /opt/signal-player
  /opt/signal-player/venv/bin/python -c "import fastapi, httpx, uvicorn; import app.agent, app.main; print(\"player imports OK\")"
  test -x /opt/signal-player/bin/signal-player-kiosk
  test -f /lib/systemd/system/signal-player.service
  test -f /etc/xdg/autostart/signal-player-kiosk.desktop
'
