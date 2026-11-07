#!/usr/bin/env bash
# One-time durable GitHub Actions SSH key; each authorization lasts five hours.
# Run as root from the checked-out Refit repository on the Vultr VM.
set -euo pipefail

[[ "$(id -u)" == 0 ]] || { echo 'Run as root on the Vultr VM.' >&2; exit 2; }
REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
[[ "$REPO" == /opt/refit-app ]] || { echo 'Expected the Refit checkout at /opt/refit-app.' >&2; exit 2; }
command -v ssh-keygen >/dev/null
command -v flock >/dev/null
command -v systemctl >/dev/null
[[ -f /etc/ssh/ssh_host_ed25519_key.pub ]] || { echo 'Ed25519 host key missing. Check sshd.' >&2; exit 2; }

DIRECTORY=/etc/refit/host-ssh
PRIVATE="$DIRECTORY/identity_ed25519"
PUBLIC="$PRIVATE.pub"
CONFIG="$DIRECTORY/budgets.env"
COMMAND=/usr/local/sbin/refit-host-ssh-command
KEY_COMMENT=refit-github-five-hour-bridge
AUTHORIZED=/root/.ssh/authorized_keys

install -d -o root -g root -m 0700 "$DIRECTORY" /root/.ssh
install -o root -g root -m 0750 "$REPO/deploy/refit-host-ssh-command.sh" "$COMMAND"
[[ ! -L "$AUTHORIZED" ]] || { echo 'Refusing symlinked authorized_keys.' >&2; exit 2; }
touch "$AUTHORIZED"
chmod 0600 "$AUTHORIZED"

FIRST_SETUP=0
if [[ ! -s "$PUBLIC" ]]; then
  [[ ! -e "$PRIVATE" ]] || { echo 'Private key exists without a public key: inspect manually.' >&2; exit 2; }
  ssh-keygen -q -t ed25519 -N '' -f "$PRIVATE" -C "$KEY_COMMENT"
  chmod 0600 "$PRIVATE"
  chmod 0644 "$PUBLIC"
  FIRST_SETUP=1
fi

# Keep the current quotas rather than unintentionally replacing 72, 128, etc.
if [[ ! -e "$CONFIG" ]]; then
  SERVICE=/etc/systemd/system/refit-application.service
  DAILY="$(sed -nE 's/.*--daily-budget ([0-9]+).*/\1/p' "$SERVICE" 2>/dev/null | tail -1)"
  ACCOUNT="$(sed -nE 's/.*--account-daily-budget ([0-9]+).*/\1/p' "$SERVICE" 2>/dev/null | tail -1)"
  DAILY="${DAILY:-72}"
  ACCOUNT="${ACCOUNT:-16}"
  [[ "$DAILY" =~ ^[0-9]{1,4}$ && "$ACCOUNT" =~ ^[0-9]{1,3}$ ]] || {
    echo 'Could not detect existing numeric limits.' >&2; exit 2;
  }
  (( DAILY >= 1 && DAILY <= 2048 && ACCOUNT >= 1 && ACCOUNT <= 512 )) || {
    echo 'Existing quotas exceed supported application limits.' >&2; exit 2;
  }
  ( umask 077; printf 'REFIT_APPLICATION_DAILY_BUDGET=%s\nREFIT_APPLICATION_ACCOUNT_DAILY_BUDGET=%s\n' \
    "$DAILY" "$ACCOUNT" > "$CONFIG" )
fi

EXPIRY="$(date -u -d '+5 hours' '+%Y%m%d%H%M%SZ')"
PUB_KEY="$(awk '{print $1 " " $2}' "$PUBLIC")"
TEMP="$(mktemp /root/.ssh/refit-keys.XXXXXXXX)"
chmod 0600 "$TEMP"
# Only replace this dedicated, recognizable public-key line. Preserve all other access.
awk -v marker="$KEY_COMMENT" '$0 !~ (" " marker "$")' "$AUTHORIZED" > "$TEMP"
printf 'restrict,expiry-time="%s",command="%s" %s %s\n' \
  "$EXPIRY" "$COMMAND" "$PUB_KEY" "$KEY_COMMENT" >> "$TEMP"
cat "$TEMP" > "$AUTHORIZED"
rm -f "$TEMP"

printf '\nRefit SSH bridge authorized until %s (UTC).\n' "$EXPIRY"
ssh-keygen -lf "$PUBLIC"
printf 'Budgets retained in %s\n' "$CONFIG"
printf '\nGitHub repository: Davemafy/refit\n'
printf 'Actions secret 1: REFIT_HOST_SSH_PRIVATE_KEY\n'
printf 'Actions secret 2: REFIT_HOST_KNOWN_HOSTS\n'
if [[ "$FIRST_SETUP" == 1 || "${1:-}" == --show-key ]]; then
  printf '\n--- BEGIN PRIVATE KEY: paste into GitHub Actions secret, NEVER into ChatGPT ---\n'
  cat "$PRIVATE"
  printf '\n--- END PRIVATE KEY ---\n'
else
  echo 'SSH private key is unchanged. Existing GitHub secret remains valid.'
  echo 'If needed, rerun with --show-key to reconfigure the secret securely.'
fi
printf '\n--- BEGIN PINNED HOST ENTRY: paste into GitHub Actions secret ---\n'
printf '80.240.30.92 %s\n' "$(awk '{print $1 " " $2}' /etc/ssh/ssh_host_ed25519_key.pub)"
printf '%s\n' '--- END PINNED HOST ENTRY ---'
printf '\nNever commit either credential. To renew access for another five hours, rerun:\n'
printf '  cd /opt/refit-app && sudo bash deploy/setup-github-ssh-access.sh\n'
printf 'The same private key is reused; GitHub secrets need not be updated.\n'
