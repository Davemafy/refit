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
[[ "$IMAGE" =~ ^[a-z0-9][a-z0-9_.:-]{0,100}$ && "$BUDGET" =~ ^[0-9]{1,2}$ ]] && ((BUDGET >= 1 && BUDGET <= 96))
docker build -f "$REPO/integrations/application/Dockerfile" -t "$IMAGE" "$REPO"
getent group docker >/dev/null
id refit-application >/dev/null 2>&1 || useradd --system --home-dir /var/lib/refit-application --shell /usr/sbin/nologin refit-application
install -d -m 0700 -o refit-application -g refit-application /var/lib/refit-application
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
ExecStart=/usr/bin/python3 -m scripts.application_http --state /var/lib/refit-application --port 8098 --image $IMAGE --daily-budget $BUDGET
UMask=0077
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
ProtectHome=true
ProtectSystem=strict
PrivateTmp=true
ReadWritePaths=/var/lib/refit-application
MemoryMax=512M
TasksMax=64

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now refit-application
systemctl restart refit-application
for attempt in {1..15}; do
  if curl --max-time 2 -fsS http://127.0.0.1:8098/bring >/dev/null; then
    echo 'Refit operator service is ready on 127.0.0.1:8098.'
    exit 0
  fi
  sleep 1
done
systemctl --no-pager status refit-application
exit 1
