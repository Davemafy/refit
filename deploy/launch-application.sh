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
# The public HTTP process is NOT a Docker client with host-root authority.
# A separate root-owned broker checks full command vectors, immutable image
# IDs, gVisor policy and staging paths. It accepts only this service UID.
if id -nG refit-application | tr ' ' '\n' | grep -qx docker; then
  gpasswd -d refit-application docker >/dev/null
fi
install -d -m 0755 -o root -g root /usr/local/libexec/refit /usr/local/libexec/refit-cli
install -m 0755 -o root -g root "$REPO/scripts/docker_guard.py" /usr/local/libexec/refit/docker-guard.py
ln -sfn /usr/local/libexec/refit/docker-guard.py /usr/local/libexec/refit-cli/docker
python3 - "$IMAGE_ID" "$DIAGNOSTIC_IMAGE_ID" <<'PY'
import json,sys
from pathlib import Path
p=Path("/etc/refit/docker-guard.json")
p.write_text(json.dumps({"application":sys.argv[1],"diagnostic":sys.argv[2]})+"\n")
p.chmod(0o600)
PY
cat > /etc/systemd/system/refit-docker-guard.service <<UNIT
[Unit]
Description=Refit restricted gVisor Docker command broker
Requires=docker.service
After=docker.service

[Service]
Type=simple
User=root
Group=root
ExecStart=/usr/bin/python3 -I /usr/local/libexec/refit/docker-guard.py --server
RuntimeDirectory=refit-docker-guard
RuntimeDirectoryMode=0755
Restart=on-failure
RestartSec=2
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectKernelLogs=true
ProtectControlGroups=true
RestrictAddressFamilies=AF_UNIX
ReadWritePaths=/run/refit-docker-guard /var/lib/refit-application/sandbox-staging
MemoryMax=160M
TasksMax=64

[Install]
WantedBy=multi-user.target
UNIT
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
WorkingDirectory=$REPO
EnvironmentFile=/etc/refit/inference.env
EnvironmentFile=/etc/refit/application.env
EnvironmentFile=-/etc/refit/application-public.env
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=REFIT_DEPLOYED_REVISION=$REVISION
Environment=REFIT_ENABLE_SANDBOX_DIAGNOSTICS=1
Environment=REFIT_SANDBOX_RUNTIME=runsc
Environment=REFIT_DIAGNOSTIC_IMAGE_ID=$DIAGNOSTIC_IMAGE_ID
Environment=PATH=/usr/local/libexec/refit-cli:/usr/local/bin:/usr/bin:/bin
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
systemctl enable refit-docker-guard
systemctl restart refit-docker-guard
for attempt in $(seq 1 30); do
  test -S /run/refit-docker-guard/docker.sock && break
  sleep 0.2
done
test -S /run/refit-docker-guard/docker.sock
if id -nG refit-application | tr ' ' '\n' | grep -qx docker; then
  echo "Refit HTTP service still has privileged Docker group access" >&2
  exit 1
fi
# First prove that the unprivileged process can reach the allowlisted broker.
# The actual runsc execution receipt below is the authoritative policy gate.
runuser -u refit-application -- env PATH=/usr/local/libexec/refit-cli:/usr/bin:/bin \
  /usr/local/libexec/refit-cli/docker info --format '{{json .Runtimes}}' >/dev/null
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
    # Verify actual gVisor execution through the unprivileged controller's
    # restricted broker, not just a privileged root-only acceptance path.
    (
      cd "$REPO"
      runuser -u refit-application -- env \
        PATH=/usr/local/libexec/refit-cli:/usr/local/bin:/usr/bin:/bin \
        REFIT_DIAGNOSTIC_IMAGE_ID="$DIAGNOSTIC_IMAGE_ID" \
        python3 -c 'from pathlib import Path; from scripts.sandbox_runner import DockerSandbox; r=DockerSandbox(runtime="runsc",staging_root=Path("/var/lib/refit-application/sandbox-staging")).run("print(\"REFIT-UNPRIVILEGED-EXECUTION\")",{},label="broker_acceptance"); import json; print("Unprivileged broker receipt",json.dumps({k:r.get(k) for k in ("status","exit_code","timed_out","container_created","container_removed_verified","ledger_valid","startup_error","runtime_identity","stderr")})[:1500],flush=True); assert r["status"]=="passed" and "REFIT-UNPRIVILEGED-EXECUTION" in r["stdout"] and r["container_removed_verified"] and r["ledger_valid"]; print("Unprivileged broker gVisor execution and cleanup verified")'
    )
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
    PYTHONPATH="$REPO" python3 -m scripts.c1_public_receipt \
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
