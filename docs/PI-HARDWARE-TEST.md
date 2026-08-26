# Raspberry Pi 4 installation and first hardware test

## Supported first-test platform

Use a Raspberry Pi 4 with Raspberry Pi OS **64-bit Desktop**, based on Debian
Bookworm, and an HDMI display in landscape orientation. Desktop is required:
the package deliberately uses LightDM to create a real graphical user session
and an XDG autostart entry to run Chromium. This is more reliable on Bookworm
than trying to give a system service a guessed `DISPLAY` or Wayland socket.

For the first validation, configure Ethernet in Raspberry Pi Imager. Pre-set
Wi-Fi is also fine; Wi-Fi captive-portal setup is not part of V1.

## Install

1. Flash Raspberry Pi OS 64-bit Desktop with Raspberry Pi Imager and boot it
   with the TV/monitor attached.
2. Copy `signal-player_0.1.0-rc1_arm64.deb` to the Pi (or download it from the
   reviewed build artifact).
3. Install and configure the public Signal server URL:

   ```bash
   sudo apt update
   sudo apt install ./signal-player_0.1.0-rc1_arm64.deb
   sudo signal-player config set-server https://signal.example.org
   sudo reboot
   ```

   Do not use `127.0.0.1` for `server_url`: that would point the Pi at itself.
   The configured URL must be the externally reachable Signal hostname with a
   valid TLS certificate.

At boot, `signal-player.service` starts the local agent at
`http://127.0.0.1:8090`. LightDM signs in the restricted `signal-player` user,
and its XDG autostart entry launches Chromium in kiosk mode at the local
`/player` page. The agent never waits for `network-online.target`, so cached
content can start before DNS or Signal is available.

## Enroll

1. Confirm the full-screen Signal enrollment screen appears; the mouse remains
   visible during setup.
2. In the Signal console, create the Player and generate a current enrollment
   code.
3. Type the code on the Pi using an attached USB keyboard/mouse and select
   **Connect**.
4. Confirm the console shows the Player online and that `sudo signal-player
   status` reports `Enrollment: enrolled`.
5. Verify identity persistence with `sudo reboot`; the Pi must not request a
   new code.

Enrollment is outbound from the Pi. Signal does not need an inbound connection
to the Pi. If a server credential needs to be revoked, remove/re-enroll the
Player in Signal as well as running `sudo signal-player reset-enrollment`.

## Playback and display checklist

Mark each item on the physical hardware:

- [ ] A Signal Design plays at 1920×1080 with correct edges, text, and scaling.
- [ ] JPG/PNG, PDF, and video play.
- [ ] Fit to Display contains media; Fill Display crops as expected.
- [ ] Durations, rotation, and transitions occur without browser chrome.
- [ ] The cursor is hidden during content playback and audio is silent.
- [ ] The desktop is not exposed after boot.
- [ ] An available 4K TV is tested at 3840×2160 (not a prerequisite for first
      hardware approval).

Chromium is invoked with `--kiosk`, `--noerrdialogs`, `--disable-infobars`,
`--disable-session-crashed-bubble`, `--disable-features=Translate`,
`--autoplay-policy=no-user-gesture-required`, `--mute-audio`, `--no-first-run`,
and `--no-default-browser-check`. Its session launcher restarts it three
seconds after an exit. HDMI unplug/replug and TV power-state recovery remain
physical-device checks because compositor behavior is Pi/TV dependent.

## Resilience checklist

- [ ] Reboot while connected: cached signage returns without reenrollment.
- [ ] After synchronization, disconnect Ethernet/Wi-Fi: rotation continues.
- [ ] Reboot while offline: cached manifest and media still appear.
- [ ] Reconnect networking: sync and heartbeat resume.
- [ ] Stop the Signal API temporarily: playback continues; restart it and
      confirm the player reconnects without a screen flash when unchanged.
- [ ] Kill Chromium: it returns automatically within a few seconds.
- [ ] Restart/kill the agent: `systemd` restarts it; inspect
      `journalctl -u signal-player -f`.
- [ ] Power-cycle the Pi and repeat the reboot expectation.

Pi OS should retain normal NTP/timezone configuration. Scheduling uses the
existing IANA timezone values in Signal; this package does not hard-code EST
or install a separate time service.

## Diagnostics and maintenance

```bash
sudo signal-player status
sudo signal-player config show
sudo signal-player config set-server https://signal.example.org
sudo signal-player reset-enrollment       # preserves cached signage
sudo signal-player clear-cache            # refills on next sync
sudo journalctl -u signal-player -f
```

`sudo signal-player factory-reset --confirm DELETE` intentionally clears local
state and restores the placeholder server URL. It requires reenrollment.

An ordinary upgrade preserves `/etc/signal-player/config.toml` and
`/var/lib/signal-player` (identity, active manifest, and cache). `apt remove
signal-player` also preserves those paths for reinstall. `apt purge
signal-player` deletes them and is a factory reset. Downgrades have not been
qualified; do not downgrade a field unit without retaining its state backup.

## Security and deployment notes

The agent only binds to `127.0.0.1`; Chromium does not enable remote debugging.
The device identity lives in `/var/lib/signal-player/identity` with restrictive
owner permissions, never in the config file or CLI output. `/opt/signal-player`
is root-owned application/runtime content, `/etc/signal-player` is root-owned
configuration (group writable only by the service account so the local setup
screen can save the URL), and `/var/lib/signal-player` is private player state.
TLS certificate verification remains enabled. Cloudflare Tunnel is optional:
the Pi only needs ordinary outbound HTTPS for enrollment, polling, commands,
and media downloads.
