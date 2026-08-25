#!/usr/bin/env bash
set -euo pipefail
docker buildx build --platform linux/arm64 --output type=local,dest=dist/player-deb -f pi/package/Dockerfile pi
