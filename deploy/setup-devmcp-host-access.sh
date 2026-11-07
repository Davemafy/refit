#!/usr/bin/env bash
# Authorize a gateway-managed public SSH key for five hours on the Refit VM.
# This script never reads or emits private keys.
set -euo pipefail

[[ "$(id -u)" == 0 ]] || { echo "Run as root on the Refit Vultr VM." >&2; exit 2; }
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
[[ "$ROOT" == /opt/refit-app ]] || {
  echo "Expected checkout at /opt/refit-app." >&2; exit 2
}
[[ $# -eq 1 ]] || {
  echo "Usage: bash deploy/setup-devmcp-host-access.sh 'ssh-ed25519 <public-key> refit-devmcp-gateway'" >&2; exit 2
}
PUBLIC="$1"
[[ "$PUBLIC" =~ ^ssh-ed25519[[:space:]][A-Za-z0-9+/=]{60,120}[[:space:]]refit-devmcp-gateway$ ]] || {
  echo "Expected an Ed25519 gateway public key without additional options." >&2; exit 2
}

FORCED=/usr/local/sbin/refit-host-ssh-command
AUTH=/root/.ssh/authorized_keys
CONFIG=/etc/refit/host-ssh/budgets.env
install -d -o root -g root -m 0700 /root/.ssh /etc/refit/host-ssh
install -o root -g root -m 0750 "$ROOT/deploy/refit-host-ssh-command.sh" "$FORCED"

# Preserve the running application's quotas rather than resetting them.
if [[ ! -f "$CONFIG" ]]; then
  SERVICE=/etc/systemd/system/refit-application.service
  DAILY="$(sed -nE 's/.*--daily-budget ([0-9]+).*/\1/p' "$SERVICE" 2>/dev/null | tail -1)"
  ACCOUNT="$(sed -nE 's/.*--account-daily-budget ([0-9]+).*/\1/p' "$SERVICE" 2>/dev/null | tail -1)"
  DAILY="${DAILY:-72}"
  ACCOUNT="${ACCOUNT:-16}"
  [[ "$DAILY" =~ ^[0-9]{1,4}$ && "$ACCOUNT" =~ ^[0-9]{1,3}$ ]] || {
    echo "Existing daily request quotas are not numeric." >&2; exit 2
  }
  (( DAILY >= 1 && DAILY <= 2048 && ACCOUNT >= 1 && ACCOUNT <= 512 )) || {
    echo "Existing quotas are outside supported bounds." >&2; exit 2
  }
  ( umask 077
    printf 'REFIT_APPLICATION_DAILY_BUDGET=%s\nREFIT_APPLICATION_ACCOUNT_DAILY_BUDGET=%s\n' \
      "$DAILY" "$ACCOUNT" > "$CONFIG"
  )
fi
[[ ! -L "$CONFIG" ]] && [[ "$(stat -c %u "$CONFIG")" == 0 ]] || {
  echo "Unsafe or non-root deployment quota file." >&2; exit 2
}
chmod 0600 "$CONFIG"

[[ ! -L "$AUTH" ]] || { echo "Refusing symlinked authorized_keys." >&2; exit 2; }
touch "$AUTH"
chmod 0600 "$AUTH"
chown root:root "$AUTH"
exec 9>/run/lock/refit-devmcp-host-access.lock
flock 9

TMPKEY="$(mktemp /root/.ssh/refit-key-test.XXXXXXXX)"
TMPAUTH="$(mktemp /root/.ssh/refit-authorized.XXXXXXXX)"
trap 'rm -f "$TMPKEY" "$TMPAUTH"' EXIT
printf '%s\n' "$PUBLIC" > "$TMPKEY"
ssh-keygen -lf "$TMPKEY" >/dev/null
EXPIRY="$(date -u -d '+5 hours' +%Y%m%d%H%M%SZ)"

# Replace only the dev-MCP entry, preserving unrelated SSH access.
awk '$0 !~ / refit-devmcp-gateway$/ && $0 !~ / refit-devmcp-five-hour-20261107$/' "$AUTH" > "$TMPAUTH"
printf 'restrict,expiry-time="%s",command="%s" %s\n' \
  "$EXPIRY" "$FORCED" "$PUBLIC" >> "$TMPAUTH"
install -o root -g root -m 0600 "$TMPAUTH" "$AUTH"
printf 'Authorized Refit gateway SSH key until %s UTC.\n' "$EXPIRY"
printf 'Client key fingerprint: '
ssh-keygen -lf "$TMPKEY"
printf 'Server SSH fingerprint (verify against the owner-supplied expected fingerprint): '
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
printf 'Forced command: status or deploy <exact 40-character Git SHA>.\n'
