#!/usr/bin/env bash
# Install the private operator service alongside the existing public evidence site.
set -euo pipefail
test "$(id -u)" -eq 0 || { echo 'Run as root on the Vultr host.' >&2; exit 2; }
REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
[[ "$REPO" =~ ^/opt/[a-zA-Z0-9_./-]+$ ]] || { echo 'Use a checkout under /opt.' >&2; exit 2; }
REVISION="$(git -C "$REPO" rev-parse --verify HEAD)"
[[ "$REVISION" =~ ^[a-f0-9]{40}$ ]]
test -z "$(git -C "$REPO" status --porcelain --untracked-files=no)" || {
  echo 'Deploy from a clean Git revision.' >&2
  exit 2
}
test -r /etc/refit/inference.env
docker info --format '{{json .Runtimes}}' | python3 -c 'import json,sys; assert "runsc" in json.load(sys.stdin)'
IMAGE="${REFIT_APPLICATION_IMAGE:-refit-application}"
BUDGET="${REFIT_APPLICATION_DAILY_BUDGET:-48}"
ACCOUNT_BUDGET="${REFIT_APPLICATION_ACCOUNT_DAILY_BUDGET:-16}"
[[ "$IMAGE" =~ ^[a-z0-9][a-z0-9_.:-]{0,100}$ &&
   "$BUDGET" =~ ^[0-9]{1,4}$ && "$ACCOUNT_BUDGET" =~ ^[0-9]{1,3}$ ]] &&
  ((BUDGET >= 1 && BUDGET <= 2048 &&
    ACCOUNT_BUDGET >= 1 && ACCOUNT_BUDGET <= 512))
# The bounded generated-Python diagnostic runs in a separate approved image.
# Pull on the trusted host at deploy time; the worker itself has no network.
docker pull python:3.11-alpine >/dev/null
DIAGNOSTIC_IMAGE_ID="$(docker image inspect --format='{{.Id}}' python:3.11-alpine)"
[[ "$DIAGNOSTIC_IMAGE_ID" =~ ^sha256:[a-f0-9]{64}$ ]]
docker build -f "$REPO/integrations/application/Dockerfile" -t "$IMAGE" "$REPO"
IMAGE_ID="$(docker image inspect --format='{{.Id}}' "$IMAGE")"
[[ "$IMAGE_ID" =~ ^sha256:[a-f0-9]{64}$ ]]
APP_COMMAND="/usr/bin/python3 -m scripts.application_http --state /var/lib/refit-application --port 8098 --image $IMAGE_ID --daily-budget $BUDGET --account-daily-budget $ACCOUNT_BUDGET"
getent group docker >/dev/null
id refit-application >/dev/null 2>&1 || useradd --system --home-dir /var/lib/refit-application --shell /usr/sbin/nologin refit-application
install -d -m 0700 -o refit-application -g refit-application /var/lib/refit-application
# Docker's daemon and systemd's PrivateTmp service must see the same
# explicitly approved mount source. The generated worker gets only a
# read-only subdirectory, never the staging root or host credentials.
install -d -m 0700 -o refit-application -g refit-application \
  /var/lib/refit-application/sandbox-staging
if [[ ! -e /etc/refit/application.env ]]; then
  (umask 077; python3 -c 'import secrets; print("REFIT_APPLICATION_TOKEN="+secrets.token_urlsafe(36))' > /etc/refit/application.env)
fi
chmod 600 /etc/refit/application.env
cat > /etc/systemd/system/refit-application.service <<UNIT
[Unit]
Description=Refit private application migration
Requires=docker.service
After=docker.service

[Service]
Type=simple
User=refit-application
Group=refit-application
SupplementaryGroups=docker
WorkingDirectory=$REPO
EnvironmentFile=/etc/refit/inference.env
EnvironmentFile=/etc/refit/application.env
EnvironmentFile=-/etc/refit/application-public.env
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=REFIT_DEPLOYED_REVISION=$REVISION
Environment=REFIT_ENABLE_SANDBOX_DIAGNOSTICS=1
Environment=REFIT_SANDBOX_RUNTIME=runsc
Environment=REFIT_DIAGNOSTIC_IMAGE_ID=$DIAGNOSTIC_IMAGE_ID
ExecStart=$APP_COMMAND
UMask=0077
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
ProtectHome=true
ProtectSystem=strict
PrivateTmp=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
ProtectKernelLogs=true
LockPersonality=true
RestrictSUIDSGID=true
ReadWritePaths=/var/lib/refit-application
MemoryMax=512M
TasksMax=64

[Install]
WantedBy=multi-user.target
UNIT
# A prior release installed the service from an immutable /opt/refit-release-* checkout.
# Existing systemd drop-ins can also pin the old worker image. Keep the checkout
# and immutable image together without removing unrelated host overrides.
install -d -m 0755 /etc/systemd/system/refit-application.service.d
cat > /etc/systemd/system/refit-application.service.d/zz-refit-managed-checkout.conf <<OVERRIDE
[Service]
WorkingDirectory=$REPO
Environment=REFIT_DEPLOYED_REVISION=$REVISION
ExecStart=
ExecStart=$APP_COMMAND
OVERRIDE
systemctl daemon-reload
SERVICE_DIRECTORY="$(systemctl show refit-application --property=WorkingDirectory --value)"
if [[ "$SERVICE_DIRECTORY" != "$REPO" ]]; then
  printf 'Refit service checkout mismatch: expected %s, got %s.\n' "$REPO" "$SERVICE_DIRECTORY" >&2
  systemctl cat refit-application >&2
  exit 1
fi
SERVICE_COMMAND="$(systemctl show refit-application --property=ExecStart --value)"
if [[ "$SERVICE_COMMAND" != *"argv[]=$APP_COMMAND ;"* ]]; then
  printf 'Refit service command does not point at the newly built worker %s.\n' "$IMAGE_ID" >&2
  exit 1
fi
systemctl enable --now refit-application
systemctl restart refit-application
for attempt in {1..15}; do
  # Do not mistake the old process answering /bring for the new release.
  installed="$(curl -fsS --max-time 2 http://127.0.0.1:8098/api/application/release 2>/dev/null |
    python3 -c 'import json,sys; print(json.load(sys.stdin).get("revision", ""))' 2>/dev/null || true)"
  if [[ "$installed" == "$REVISION" ]] &&
     curl --max-time 2 -fsS http://127.0.0.1:8098/bring >/dev/null; then
    # Non-destructive real-host gVisor containment acceptance. Full synthetic
    # receipts remain in a root-owned file on this Vultr VM.
    install -d -o root -g root -m 0700 /var/lib/refit-application/c1-acceptance
    (
      cd "$REPO"
      REFIT_DIAGNOSTIC_IMAGE_ID="$DIAGNOSTIC_IMAGE_ID" \
        timeout --signal=TERM --kill-after=5s 2m python3 -m scripts.c1_acceptance \
        --output "/var/lib/refit-application/c1-acceptance/$REVISION.json"
    )
    # Publish only a root-attested, redacted synthetic containment receipt.
    # Never expose raw Docker or host-state receipts to the web service.
    install -d -o root -g root -m 0755 /usr/local/share/refit
    python3 -m scripts.c1_public_receipt \
      --source "/var/lib/refit-application/c1-acceptance/$REVISION.json" \
      --revision "$REVISION" \
      --output /usr/local/share/refit/c1-containment.json
    test "$(stat -c %u:%a /usr/local/share/refit/c1-containment.json)" = "0:644"
    echo "Refit application and Vultr-host containment verified at revision $REVISION with worker $IMAGE_ID."
    exit 0
  fi
  sleep 1
done
printf 'Refit operator did not start at expected revision %s.\n' "$REVISION" >&2
systemctl --no-pager status refit-application
exit 1
