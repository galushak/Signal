# Signal Player architecture

The player under `pi/` is shared by Docker and Raspberry Pi adapters. Chromium
loads the local `http://127.0.0.1:8090/player` service, never the management UI.
An enrollment code is short-lived and hashed server-side; claiming it creates a
separate random device secret, whose hash is stored on the Player and plaintext
is delivered to that device only once. Device routes use this credential, not a
human JWT.

One ETag-enabled manifest contains layout, zones, published design JSON,
assignments/schedules, and checksummed media. Media downloads complete and
validate before an atomic active-manifest swap. The local renderer evaluates
schedule dates, weekday windows, and IANA timezone locally, so cached playback
continues when the server is unavailable. Docker reports temperature as
`unsupported`. Screenshot is intentionally unsupported rather than faked.
