# Signal Player release checklist

Before attaching a player package to a future GitHub release:

- [ ] Bump the single `PLAYER_VERSION` in `pi/app/version.py`.
- [ ] Start from a clean checkout and run `docker compose config --quiet`.
- [ ] Run the player test suite: `cd pi && python -m pytest -q`.
- [ ] Run the Docker regression: `docker compose up --build -d`; enroll a Pi
      simulator, assign content, verify Fit/Fill, Force Sync, and offline play.
- [ ] Build: `./scripts/build-player-deb.sh`.
- [ ] Inspect the package metadata and contents printed by the build script.
- [ ] Validate the ARM64 installation/runtime: `./scripts/validate-player-deb.sh`.
- [ ] Run `systemd-analyze verify pi/systemd/signal-player.service` where
      systemd tooling is available.
- [ ] Record artifact filename, size, and SHA-256 from `dist/`.
- [ ] Complete the physical checklist in `docs/PI-HARDWARE-TEST.md`, including
      boot, enrollment, 1080p, offline reboot, server recovery, Chromium
      restart, power cycle, and an upgrade over a prior package.
- [ ] Ensure no device identity, cache, `.env`, or development media is inside
      the package.

The release artifact is intentionally local at
`dist/signal-player_<version>_arm64.deb`. A future reviewed GitHub release can
attach that file and its SHA-256; no release is automatically published by this
repository.
