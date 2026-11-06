#!/usr/bin/env bash
# Deploy the tested assistant-ui integration at /bridge/ on the existing VM.
# This does not replace Refit's current root UI, /demo, or /api.
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then echo "Run as root" >&2; exit 2; fi
ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
BRIDGE="$ROOT/web/assistant-bridge"
SITE="/etc/nginx/sites-available/refit"
TARGET="/var/www/refit-assistant-bridge"

if [ ! -f "$SITE" ] || [ ! -f "$BRIDGE/package-lock.json" ]; then
  echo "Refit deployment or bridge package missing. Pull main first." >&2
  exit 2
fi
if ! grep -q 'proxy_pass http://127.0.0.1:8097' "$SITE"; then
  echo "Refusing to alter unexpected Nginx config." >&2
  exit 2
fi

if ! command -v npm >/dev/null || ! command -v node >/dev/null; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y nodejs npm
fi
NODE_MAJOR="$(node -p "process.versions.node.split('.')[0]")"
if [ "$NODE_MAJOR" -lt 18 ]; then
  echo "Requires Node 18+; found $(node --version)." >&2
  exit 2
fi
cd "$BRIDGE"
npm ci --no-audit --no-fund
npm test
npm run build

if [ ! -s dist/index.html ]; then
  echo "No compiled HTML was generated." >&2
  exit 3
fi
STAGE="$(mktemp -d /var/www/refit-bridge.stage.XXXXXX)"
CONFIG_BACKUP="$(mktemp /tmp/refit-nginx-config.XXXXXX)"
cp -a "$SITE" "$CONFIG_BACKUP"
PREVIOUS=""
restore() {
  echo "Bridge deployment failed, restoring previous Nginx configuration." >&2
  cp -a "$CONFIG_BACKUP" "$SITE"
  if [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
    rm -rf "$TARGET"
    mv "$PREVIOUS" "$TARGET"
  fi
  rm -rf "$STAGE" "$CONFIG_BACKUP"
  nginx -t && systemctl reload nginx || true
}
trap restore ERR

cp -a dist/. "$STAGE/"
chmod -R a+rX "$STAGE"
if [ -d "$TARGET" ]; then
  PREVIOUS="$(mktemp -d /var/www/refit-bridge.backup.XXXXXX)"
  rmdir "$PREVIOUS"
  mv "$TARGET" "$PREVIOUS"
fi
mv "$STAGE" "$TARGET"

python3 - "$SITE" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
config = path.read_text()
if "location ^~ /bridge/" not in config:
    insertion = """
    location = /bridge {
        return 308 /bridge/;
    }
    location ^~ /bridge/ {
        alias /var/www/refit-assistant-bridge/;
        index index.html;
        try_files $uri $uri/ =404;
        add_header X-Content-Type-Options nosniff always;
        add_header Content-Security-Policy "default-src 'none'; connect-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; object-src 'none'; form-action 'self'; frame-ancestors 'none'" always;
    }
"""
    anchor = "    location / {\n"
    if anchor not in config:
        raise ValueError("Refusing to modify a custom root location")
    path.write_text(config.replace(anchor, insertion + "\n" + anchor, 1))
PY

nginx -t
systemctl reload nginx
CHECK_HOST="$(printenv REFIT_HOSTNAME || true)"
if [ -z "$CHECK_HOST" ]; then CHECK_HOST="_"; fi

INDEX="$(curl -fsS --max-time 8 -H "Host: $CHECK_HOST" http://127.0.0.1/bridge/)"
printf '%s' "$INDEX" | grep -F 'assets/index-' >/dev/null
ASSET="$(printf '%s' "$INDEX" | grep -oE '\./assets/index-[A-Za-z0-9_-]+\.js' | head -1 | sed 's#^\./##')"
if [ -z "$ASSET" ]; then
  echo "No built assistant-ui JS asset found." >&2
  exit 4
fi
ASSET_BYTES="$(curl -fsS --max-time 8 -H "Host: $CHECK_HOST" "http://127.0.0.1/bridge/$ASSET" | wc -c)"
if [ "$ASSET_BYTES" -lt 10000 ]; then
  echo "Built assistant-ui JS failed to load via Nginx." >&2
  exit 4
fi
curl -fsS --max-time 8 -H "Host: $CHECK_HOST" http://127.0.0.1/api/health | grep -F '"status": "ok"' >/dev/null
curl -fsS --max-time 8 -H "Host: $CHECK_HOST" http://127.0.0.1/demo | grep -F 'Change the model.' >/dev/null

trap - ERR
if [ -n "$PREVIOUS" ]; then rm -rf "$PREVIOUS"; fi
rm -f "$CONFIG_BACKUP"
echo
echo "REFIT_ASSISTANT_UI_BRIDGE_READY"
echo "URL: http://80.240.30.92/bridge/"
echo "Existing /api, /demo and root UI preserved; paid actions remain disabled."
