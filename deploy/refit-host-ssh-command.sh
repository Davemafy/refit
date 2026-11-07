#!/usr/bin/env bash
# Root-owned forced command for a five-hour GitHub Actions SSH authorization.
# The SSH key CANNOT obtain an interactive shell or run arbitrary commands.
set -euo pipefail

[[ "$(id -u)" == 0 ]] || { echo 'Root-only Refit deploy bridge.' >&2; exit 126; }
REPO=/opt/refit-app
CONFIG=/etc/refit/host-ssh/budgets.env
COMMAND="${SSH_ORIGINAL_COMMAND:-}"

if [[ "$COMMAND" == status ]]; then
  printf 'Repository: '
  git -C "$REPO" rev-parse HEAD
  printf 'Service: '
  systemctl is-active refit-application
  printf 'Public HTTP: '
  curl -ksS --connect-timeout 4 --max-time 8 -o /dev/null -w '%{http_code}\n' \
    https://80.240.30.92/app
  exit 0
fi

if [[ ! "$COMMAND" =~ ^deploy[[:space:]]([a-f0-9]{40})$ ]]; then
  echo 'Only status or deploy <40-character-commit-SHA> is permitted.' >&2
  exit 126
fi
TARGET="${BASH_REMATCH[1]}"

[[ -r "$CONFIG" ]] || { echo 'Missing root-owned deployment budget configuration.' >&2; exit 1; }
[[ "$(stat -c %u "$CONFIG")" == 0 ]] && [[ "$(stat -c %a "$CONFIG")" == 600 ]] || {
  echo 'Deployment budget configuration must be root-owned mode 600.' >&2; exit 1;
}
# The file is provisioned by the host operator and is never taken from repo inputs.
# shellcheck disable=SC1090
source "$CONFIG"
[[ "${REFIT_APPLICATION_DAILY_BUDGET:-}" =~ ^[0-9]{1,4}$ &&
   "${REFIT_APPLICATION_ACCOUNT_DAILY_BUDGET:-}" =~ ^[0-9]{1,3}$ ]] || {
  echo 'Invalid deployment budget configuration.' >&2; exit 1;
}
(( REFIT_APPLICATION_DAILY_BUDGET >= 1 && REFIT_APPLICATION_DAILY_BUDGET <= 2048 &&
   REFIT_APPLICATION_ACCOUNT_DAILY_BUDGET >= 1 && REFIT_APPLICATION_ACCOUNT_DAILY_BUDGET <= 512 )) || {
  echo 'Deployment budget exceeds supported bounds.' >&2; exit 1;
}
export REFIT_APPLICATION_DAILY_BUDGET REFIT_APPLICATION_ACCOUNT_DAILY_BUDGET

# Avoid concurrent deployments and reject unexpected revisions or local modifications.
exec 9>/run/lock/refit-host-deployment.lock
flock -n 9 || { echo 'Another Refit deployment is already in progress.' >&2; exit 1; }
[[ -d "$REPO/.git" ]] || { echo 'Refit checkout not found.' >&2; exit 1; }
[[ -z "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]] || {
  echo 'Tracked files are locally modified. Refusing deployment.' >&2; exit 1;
}

git -C "$REPO" fetch --quiet origin main
REMOTE=$(git -C "$REPO" rev-parse FETCH_HEAD)
[[ "$REMOTE" == "$TARGET" ]] || {
  echo "Refusing to deploy: main is $REMOTE, request was $TARGET." >&2
  exit 1
}
git -C "$REPO" merge-base --is-ancestor HEAD "$REMOTE" || {
  echo 'Current deployment is not an ancestor of requested revision.' >&2; exit 1
}
git -C "$REPO" merge --ff-only "$REMOTE"

# Time-bound the operation; retain the existing gVisor, secrets and systemd configuration.
timeout --signal=TERM --kill-after=15s 18m \
  bash "$REPO/deploy/launch-application.sh"
timeout --signal=TERM --kill-after=15s 4m \
  env REFIT_PUBLIC_IP=80.240.30.92 bash "$REPO/deploy/launch-platform-https.sh"
(
  cd "$REPO"
  python3 -m scripts.smoke_platform_https --expected-revision "$TARGET"
)
printf 'Verified Refit deployment: %s\n' "$TARGET"
