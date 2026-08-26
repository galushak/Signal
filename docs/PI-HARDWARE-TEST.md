# Raspberry Pi 4 test procedure

Install Raspberry Pi OS 64-bit with Ethernet or Wi-Fi configured through
Raspberry Pi Imager. Configure `server_url = "https://signal.example.org"` in
`/etc/signal-player/config.toml`, install `signal-player`, and enable
`signal-player.service`. In Signal, open Players → Enroll Display, enter the
display details, and generate an enrollment code. Open the local Pi player page
and enter that code; the Pi contacts Signal outbound, persists its device
credential, then starts heartbeat and playback without a restart. Package
upgrades preserve `/var/lib/signal-player`; a package purge may remove it.

For Docker, the simulator uses `SIGNAL_SERVER_URL=http://api:8000`; view it at
`http://localhost:8090`. To reset only its enrollment identity for a fresh test
while keeping unrelated server data, run:

`docker compose exec pi python -m app.agent reset-enrollment`

After enrollment, restart the Pi container and disconnect networking to verify
that its identity and cached playback survive. Wi-Fi captive-portal setup is
intentionally deferred.
