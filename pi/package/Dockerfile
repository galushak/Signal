FROM --platform=$BUILDPLATFORM debian:bookworm-slim AS build
ARG TARGETARCH
RUN test "$TARGETARCH" = "arm64"
RUN apt-get update && apt-get install -y --no-install-recommends dpkg-dev python3 && rm -rf /var/lib/apt/lists/*
COPY app /opt/signal-player/app
COPY requirements.txt /opt/signal-player/requirements.txt
COPY systemd/signal-player.service /opt/package/lib/systemd/system/signal-player.service
RUN mkdir -p /opt/package/DEBIAN /opt/package/opt/signal-player /opt/package/var/lib/signal-player \
 && cp -a /opt/signal-player/. /opt/package/opt/signal-player/ \
 && printf 'Package: signal-player\nVersion: 0.1.0\nArchitecture: arm64\nMaintainer: Signal\nDepends: python3, chromium\nDescription: Signal digital signage player\n' > /opt/package/DEBIAN/control \
 && dpkg-deb --build /opt/package /signal-player_0.1.0_arm64.deb
FROM scratch
COPY --from=build /signal-player_0.1.0_arm64.deb /signal-player_0.1.0_arm64.deb
