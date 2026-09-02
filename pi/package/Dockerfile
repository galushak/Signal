FROM --platform=$TARGETPLATFORM debian:bookworm-slim AS python311
ARG TARGETARCH
RUN test "$TARGETARCH" = "arm64"
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates python3 python3-pip python3-venv \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /opt/signal-player/requirements.txt
RUN python3 -m venv /opt/signal-player/venv \
 && /opt/signal-player/venv/bin/pip install --no-cache-dir --only-binary=:all: -r /opt/signal-player/requirements.txt

FROM --platform=$TARGETPLATFORM debian:trixie-slim AS python313
ARG TARGETARCH
RUN test "$TARGETARCH" = "arm64"
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates python3 python3-pip python3-venv \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /opt/signal-player/requirements.txt
RUN python3 -m venv /opt/signal-player/venv \
 && /opt/signal-player/venv/bin/pip install --no-cache-dir --only-binary=:all: -r /opt/signal-player/requirements.txt

FROM --platform=$BUILDPLATFORM debian:bookworm-slim AS package
ARG TARGETARCH
ARG PACKAGE_VERSION=0.1.0-rc1
RUN test "$TARGETARCH" = "arm64" \
 && apt-get update \
 && apt-get install -y --no-install-recommends dpkg-dev \
 && rm -rf /var/lib/apt/lists/*
COPY app /opt/package/opt/signal-player/app
COPY systemd/signal-player.service /opt/package/lib/systemd/system/signal-player.service
COPY package/config.toml /opt/package/usr/share/signal-player/config.toml
COPY package/signal-player-kiosk /opt/package/opt/signal-player/bin/signal-player-kiosk
COPY package/signal-player-kiosk.desktop /opt/package/etc/xdg/autostart/signal-player-kiosk.desktop
COPY package/50-signal-player.conf /opt/package/etc/lightdm/lightdm.conf.d/50-signal-player.conf
COPY package/postinst package/prerm package/postrm /opt/package/DEBIAN/
COPY --from=python311 /opt/signal-player/venv /opt/package/opt/signal-player/venv-py311
COPY --from=python313 /opt/signal-player/venv /opt/package/opt/signal-player/venv-py313
RUN mkdir -p /opt/package/usr/bin /out \
 && printf '%s\n' \
      '#!/bin/sh' \
      'set -eu' \
      'case "$(python3 -c "import sys; print(f\"{sys.version_info.major}.{sys.version_info.minor}\")")" in' \
      '  3.11) runtime=/opt/signal-player/venv-py311/bin/python ;;' \
      '  3.13) runtime=/opt/signal-player/venv-py313/bin/python ;;' \
      '  *) echo "Unsupported system Python. Signal Player supports Python 3.11 and 3.13." >&2; exit 1 ;;' \
      'esac' \
      'exec "$runtime" "$@"' > /opt/package/opt/signal-player/bin/signal-player-python \
 && printf '%s\n' '#!/bin/sh' 'cd /opt/signal-player' 'exec /opt/signal-player/bin/signal-player-python -m app.cli "$@"' > /opt/package/usr/bin/signal-player \
 && printf 'Package: signal-player\nVersion: %s\nArchitecture: arm64\nMaintainer: Signal <support@signal.invalid>\nDepends: python3 (>= 3.11), chromium, lightdm\nDescription: Signal digital signage player\n Signal Player runs the local, offline-capable signage agent and kiosk renderer.\n' "$PACKAGE_VERSION" > /opt/package/DEBIAN/control \
 && chmod 0755 /opt/package/usr/bin/signal-player /opt/package/opt/signal-player/bin/signal-player-python /opt/package/opt/signal-player/bin/signal-player-kiosk /opt/package/DEBIAN/postinst /opt/package/DEBIAN/prerm /opt/package/DEBIAN/postrm \
 && chmod 0644 /opt/package/lib/systemd/system/signal-player.service /opt/package/etc/xdg/autostart/signal-player-kiosk.desktop /opt/package/etc/lightdm/lightdm.conf.d/50-signal-player.conf /opt/package/usr/share/signal-player/config.toml \
 && dpkg-deb --root-owner-group --build /opt/package /out/signal-player_${PACKAGE_VERSION}_arm64.deb
FROM scratch
COPY --from=package /out/ /
