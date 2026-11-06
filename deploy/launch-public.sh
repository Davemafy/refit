#!/usr/bin/env bash
# Deploy Refit's real API and independent backup demo to an Ubuntu Vultr VM.
# Run as root from a local clone under /opt, e.g. /opt/refit-app.
# Read-only public mode: no inference keys, Docker privileges, or paid actions.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo bash deploy/launch-public.sh" >&2
  exit 2
fi
command -v systemctl >/dev/null || { echo "systemd required" >&2; exit 2; }
command -v python3 >/dev/null || { echo "Python3 required" >&2; exit 2; }
command -v apt-get >/dev/null || { echo "Ubuntu/Debian apt required" >&2; exit 2; }
REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [[ "${REPO}" == *" "* || "${REPO}" == *"'"* ]]; then
  echo "Use a repository path without whitespace or apostrophes" >&2; exit 2
fi
if [ ! -r "${REPO}/scripts/refit_http.py" ] || [ ! -r "${REPO}/web/demo/index.html" ]; then
  echo "Refit API or demo interface not found under ${REPO}" >&2; exit 2
fi

HOSTNAME_OPTION="${REFIT_HOSTNAME:-}"
if [ -n "${HOSTNAME_OPTION}" ] && ! [[ "${HOSTNAME_OPTION}" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]{0,251}[a-zA-Z0-9]$ ]]; then
  echo "REFIT_HOSTNAME must be a valid DNS hostname" >&2; exit 2
fi
echo "Refit deployment preflight: ${REPO}"
cd "${REPO}"
python3 -m compileall -q scripts tests
python3 -m unittest discover -s tests -p 'test_refit*.py' -q

if ! command -v nginx >/dev/null; then
  echo "Installing nginx reverse proxy..."
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y nginx
fi
if ! id -u refit >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/refit --shell /usr/sbin/nologin refit
fi

install -d -m 0750 -o refit -g refit /var/lib/refit /var/lib/refit/runs
# The unprivileged public service needs only read access to the checkout.
if ! runuser -u refit -- test -r "${REPO}/web/demo/index.html"; then
  echo "The 'refit' service user cannot read ${REPO}. Use /opt/refit-app." >&2
  exit 3
fi

if [ -z "${HOSTNAME_OPTION}" ]; then
  # Only disable Ubuntu's *unmodified stock* Nginx example site. Never
  # silently replace an existing custom application.
  if [ -L /etc/nginx/sites-enabled/default ]; then
    DEFAULT_PATH="$(readlink -f /etc/nginx/sites-enabled/default)"
    if grep -q 'root /var/www/html;' "${DEFAULT_PATH}"; then
      rm /etc/nginx/sites-enabled/default
    else
      echo "Custom default Nginx website detected; pass REFIT_HOSTNAME." >&2
      exit 3
    fi
  fi
  SERVER_LINE='listen 80 default_server;'
  SERVER_NAME='_'
  IPV6_LINE='listen [::]:80 default_server;'
else
  SERVER_LINE='listen 80;'
  SERVER_NAME="${HOSTNAME_OPTION}"
  IPV6_LINE='listen [::]:80;'
fi

# Preserve a previous release's config if Nginx validation fails.
NGINX_CONF=/etc/nginx/sites-available/refit
cp -f "${NGINX_CONF}" "${NGINX_CONF}.previous" 2>/dev/null || true
cat > "${NGINX_CONF}" <<EOF
server {
    ${SERVER_LINE}
    ${IPV6_LINE}
    server_name ${SERVER_NAME};
    server_tokens off;
    client_max_body_size 8k;
    client_body_timeout 10s;
    keepalive_timeout 15s;

    # API remains on Python even after the separate Next/React UI replaces /.
    location ^~ /api/ {
        proxy_pass http://127.0.0.1:8097;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_read_timeout 30s;
        proxy_hide_header Server;
    }
    # Keep the zero-dependency integration demo available as a fallback.
    location ^~ /demo {
        proxy_pass http://127.0.0.1:8097;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
    }
    # Replace only this block's upstream when the other UI is ready.
    location / {
        proxy_pass http://127.0.0.1:8097;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
    }
}
EOF
ln -sfn "${NGINX_CONF}" /etc/nginx/sites-enabled/refit
if ! nginx -t; then
  echo "Nginx config validation failed. Restoring prior config." >&2
  if [ -f "${NGINX_CONF}.previous" ]; then
    mv -f "${NGINX_CONF}.previous" "${NGINX_CONF}"
  else
    rm -f /etc/nginx/sites-enabled/refit "${NGINX_CONF}"
  fi
  exit 3
fi

SERVICE=/etc/systemd/system/refit-public.service
cat > "${SERVICE}" <<EOF
[Unit]
Description=Refit read-only public demo and migration API
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=refit
Group=refit
WorkingDirectory=${REPO}
ExecStart=/usr/bin/python3 -m scripts.refit_http --host 127.0.0.1 --port 8097 --runs-dir /var/lib/refit/runs
Environment=PYTHONUNBUFFERED=1
Environment=REFIT_ENABLE_LIVE=0
Environment=REFIT_ENABLE_SANDBOX_DIAGNOSTICS=0
Restart=on-failure
RestartSec=2s
StartLimitIntervalSec=90
StartLimitBurst=5
UMask=0077
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ProtectControlGroups=true
ProtectKernelModules=true
ProtectKernelTunables=true
PrivateTmp=true
PrivateDevices=true
LockPersonality=true
MemoryMax=500M
TasksMax=100
ReadWritePaths=/var/lib/refit/runs

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now refit-public
systemctl restart refit-public

READY=0
for _ in $(seq 1 30); do
  if curl -fsS --max-time 2 http://127.0.0.1:8097/api/health >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 1
done
if [ "${READY}" != 1 ]; then
  systemctl --no-pager --full status refit-public || true
  journalctl -u refit-public -n 30 --no-pager || true
  echo "Refit service did not become healthy" >&2
  exit 4
fi

python3 - <<'PY'
import json
from urllib.request import urlopen
base = "http://127.0.0.1:8097"
with urlopen(base + "/api/runs", timeout=4) as response:
    runs = json.load(response)["runs"]
assert any(r["status"] == "verified_adaptation" for r in runs)
assert any(r["status"] == "compatible_on_sample" for r in runs)
with urlopen(base + "/demo", timeout=4) as response:
    html = response.read().decode()
assert "Change the model." in html and "Interpret request" in html
with urlopen(base + "/api/capabilities", timeout=4) as response:
    capabilities = json.load(response)
assert capabilities["live_runs_enabled"] is False
print("PASS: same-origin demo, API, recorded evidence, and disabled paid actions")
PY

systemctl enable --now nginx
systemctl reload nginx

# Confirm the actual public-facing reverse-proxy path, not just Python.
# Nginx chooses the virtual host by request Host, not just default_server.
# Existing sites may explicitly claim "localhost", returning their own 404.
# Query the precise Refit server_name (the literal '_' fallback) instead.
CHECK_HOST="${HOSTNAME_OPTION:-_}"
echo "Checking Nginx route for Host: ${CHECK_HOST}"
if ! curl -fsS --max-time 6 -H "Host: ${CHECK_HOST}" http://127.0.0.1/api/health \
    | grep -F '"status": "ok"' >/dev/null; then
  echo "Nginx API proxy failed for the Refit virtual host. Active sites:" >&2
  ls -l /etc/nginx/sites-enabled/ >&2
  echo "Request diagnostics:" >&2
  curl -sS -i --max-time 6 -H "Host: ${CHECK_HOST}" http://127.0.0.1/api/health | head -n 20 >&2 || true
  exit 5
fi
if ! curl -fsS --max-time 6 -H "Host: ${CHECK_HOST}" http://127.0.0.1/demo \
    | grep -F 'Change the model.' >/dev/null; then
  echo "Nginx demo proxy failed for Host: ${CHECK_HOST}" >&2
  curl -sS -i --max-time 6 -H "Host: ${CHECK_HOST}" http://127.0.0.1/demo | head -n 20 >&2 || true
  exit 5
fi
echo "PASS: Nginx serves Refit API and demo for Host: ${CHECK_HOST}"
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q '^Status: active'; then
  ufw allow 80/tcp
fi

if [ -n "${HOSTNAME_OPTION}" ]; then
  URL="http://${HOSTNAME_OPTION}/"
else
  IP="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '/src/ { for (i=1; i<=NF; i++) if ($i=="src") { print $(i+1); exit }}')"
  URL="http://${IP:-YOUR_VULTR_IP}/"
fi
echo
echo "REFIT_PUBLIC_READY"
echo "URL: ${URL}"
echo "DEMO: ${URL}demo"
echo "API: ${URL}api/health"
echo "SERVICE: refit-public (systemd, restricted non-root)"
echo "SECURITY: public read-only, no Vultr key exposed, paid actions disabled."
echo "Next: point a DNS domain to this VM and configure HTTPS before enabling operator controls."
