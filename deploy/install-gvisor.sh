#!/usr/bin/env bash
# Install signed gVisor runsc package and register an opt-in Docker runtime.
# Must be executed by a trusted operator on the Vultr host; no default switch.
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root (sudo bash deploy/install-gvisor.sh)" >&2
  exit 2
fi
command -v docker >/dev/null || { echo "Docker not installed" >&2; exit 2; }
command -v apt-get >/dev/null || { echo "Requires Ubuntu/Debian apt" >&2; exit 2; }

# The signed upstream apt repo is preferable to unverified shell downloads.
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y   apt-transport-https ca-certificates curl gnupg

curl -fsSL https://gvisor.dev/archive.key | gpg --batch --yes --dearmor   -o /usr/share/keyrings/gvisor-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/gvisor-archive-keyring.gpg] https://storage.googleapis.com/gvisor/releases release main"   > /etc/apt/sources.list.d/gvisor.list

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y runsc
runsc install

# A reload preserves the existing Docker workload where supported.
# Avoid changing the default runtime and avoid daemon restart here.
systemctl reload docker || {
  echo "Docker reload failed. Operator must schedule a Docker restart." >&2
  exit 3
}

docker info --format '{{json .Runtimes}}' | grep -q '"runsc"' || {
  echo "runsc not registered in Docker runtimes" >&2
  exit 3
}
echo "gVisor $(runsc --version | head -n 1)"
docker run --runtime=runsc --rm python:3.11-alpine python -c   'print("gVisor Python runtime: OK")'
echo "runsc registered and executable; default Docker runtime unchanged."
