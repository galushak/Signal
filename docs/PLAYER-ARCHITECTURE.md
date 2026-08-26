# Signal Player architecture

The player under `pi/` is shared by Docker and Raspberry Pi adapters. Chromium
loads the local `http://127.0.0.1:8090/player` service, never the management UI.
An administrator prepares a Player record and Signal generates a short-lived,
single-use code. The Pi user enters that code locally; the Pi calls the stable
configured Signal hostname outbound and receives a separate random device
secret exactly once. The code is hashed for validation and its short-lived
display copy is removed when consumed, cancelled, or replaced. The device
secret is hashed on the Player; device routes use it, never a human JWT.

The physical-player server address is stored in `/etc/signal-player/config.toml`
(`server_url = "https://signal.example.org"`). The Docker simulator receives
`SIGNAL_SERVER_URL=http://api:8000` through Compose. Normal management never
opens a server-to-Pi connection and a reported IP is diagnostic information
only. To intentionally reset an unenrolled development player while preserving
cached signage, run `docker compose exec pi python -m app.agent reset-enrollment`.

One ETag-enabled manifest contains layout, zones, published design JSON,
assignments/schedules, and checksummed media. Media downloads complete and
validate before an atomic active-manifest swap. The local renderer evaluates
schedule dates, weekday windows, and IANA timezone locally, so cached playback
continues when the server is unavailable. Docker reports temperature as
`unsupported`. Screenshot is intentionally unsupported rather than faked.

For Raspberry Pi OS 64-bit Desktop (Bookworm), the production package runs the
same player core in a `signal-player.service` system service bound only to
localhost. A LightDM autologin session for the dedicated `signal-player` user
starts Chromium through an XDG autostart entry, avoiding a fragile assumption
that a system service owns the active X11/Wayland display. The agent uses
systemd restart/backoff; the session launcher loops Chromium after a crash.
Application and package-local Python dependencies are immutable under
`/opt/signal-player`, while configuration and durable identity/cache remain in
`/etc/signal-player` and `/var/lib/signal-player` through upgrades.
