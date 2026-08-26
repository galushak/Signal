#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
version=$(sed -n 's/^PLAYER_VERSION = "\([^"]*\)"/\1/p' "$root/pi/app/version.py")
if [[ -z "$version" ]]; then
  echo "Unable to read PLAYER_VERSION from pi/app/version.py" >&2
  exit 1
fi

destination="$root/dist"
mkdir -p "$destination"
docker buildx build \
  --platform linux/arm64 \
  --build-arg "PACKAGE_VERSION=$version" \
  --output "type=local,dest=$destination" \
  -f "$root/pi/package/Dockerfile" "$root/pi"

artifact="$destination/signal-player_${version}_arm64.deb"
test -f "$artifact"
echo "Built $artifact"
dpkg-deb --info "$artifact"
dpkg-deb --contents "$artifact"
echo "SHA-256: $(sha256sum "$artifact" | awk '{print $1}')"
