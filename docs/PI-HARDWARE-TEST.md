# Raspberry Pi 4 test procedure

Install Raspberry Pi OS 64-bit with Ethernet or Wi-Fi configured through
Raspberry Pi Imager. Install `signal-player`, enable `signal-player.service`,
and enroll its local player page in Signal. Package upgrades preserve
`/var/lib/signal-player`; a package purge may remove it. Disconnect networking
after a successful sync to validate cached playback and local schedule expiry.
Wi-Fi captive-portal setup is intentionally deferred.
