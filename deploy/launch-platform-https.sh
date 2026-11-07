#!/usr/bin/env bash
# Add the authenticated platform on :443 beside the existing HTTP evidence site.
set -euo pipefail
test "$(id -u)" -eq 0
IP="${REFIT_PUBLIC_IP:?Set REFIT_PUBLIC_IP to the public IPv4 address of this VM}"
python3 -c 'import ipaddress,sys; assert ipaddress.IPv4Address(sys.argv[1]).is_global' "$IP"
CERTBOT="${REFIT_CERTBOT:-/opt/refit-certbot/bin/certbot}"
test -x "$CERTBOT"
HTTP_SITE=/etc/nginx/sites-available/refit
test -f "$HTTP_SITE"
install -d -m 0755 /var/www/refit-acme/.well-known/acme-challenge
if ! grep -q 'refit-platform-acme' "$HTTP_SITE"; then
  cp -p "$HTTP_SITE" "$HTTP_SITE.before-platform"
  python3 - "$HTTP_SITE" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
s = path.read_text()
assert s.count("server {") == 1
path.write_text(s.replace("server {", """server {
    # refit-platform-acme
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/refit-acme;
        try_files $uri =404;
    }""", 1))
PY
  if ! nginx -t; then
    cp -p "$HTTP_SITE.before-platform" "$HTTP_SITE"
    exit 1
  fi
  systemctl reload nginx
fi
"$CERTBOT" certonly --webroot -w /var/www/refit-acme --ip-address "$IP" \
  --preferred-profile shortlived --cert-name refit-platform-ip --non-interactive \
  --agree-tos --register-unsafely-without-email --keep-until-expiring

cat > /etc/nginx/snippets/refit-platform-proxy.conf <<'NGINX'
proxy_pass http://127.0.0.1:8098;
proxy_http_version 1.1;
proxy_set_header Host $host;
proxy_set_header X-Refit-Public 1;
proxy_set_header Authorization "";
proxy_buffering off;
proxy_read_timeout 30s;
proxy_hide_header Server;
NGINX
cat > /etc/nginx/sites-available/refit-platform <<NGINX
limit_req_zone \$binary_remote_addr zone=refit_login:1m rate=5r/m;
limit_conn_zone \$binary_remote_addr zone=refit_connections:1m;
server {
    listen 443 ssl;
    server_name $IP;
    ssl_certificate /etc/letsencrypt/live/refit-platform-ip/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/refit-platform-ip/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    server_tokens off;
    client_max_body_size 6m;
    client_body_timeout 15s;
    limit_conn refit_connections 12;
    add_header Strict-Transport-Security "max-age=86400" always;

    location = / { include snippets/refit-platform-proxy.conf; }
    location = /docs { include snippets/refit-platform-proxy.conf; }
    location = /login { include snippets/refit-platform-proxy.conf; }
    location = /signup { include snippets/refit-platform-proxy.conf; }
    location = /bring { include snippets/refit-platform-proxy.conf; }
    location ^~ /assets/ { include snippets/refit-platform-proxy.conf; }
    location = /app { include snippets/refit-platform-proxy.conf; }
    location ^~ /app/ { include snippets/refit-platform-proxy.conf; }
    location = /api/application { include snippets/refit-platform-proxy.conf; }
    location ~ ^/api/application/(login|register)$ {
        limit_req zone=refit_login burst=6 nodelay;
        limit_req_status 429;
        client_max_body_size 2k;
        include snippets/refit-platform-proxy.conf;
    }
    location /api/application/ { include snippets/refit-platform-proxy.conf; }
    location / { return 404; }
}
NGINX
umask 077
printf 'REFIT_PUBLIC_ORIGIN=https://%s\n' "$IP" > /etc/refit/application-public.env
# Enable account enforcement before opening the HTTPS proxy.
systemctl restart refit-application
for _ in {1..15}; do
  if curl -fsS -H 'X-Refit-Public: 1' http://127.0.0.1:8098/api/application/session |
    python3 -c 'import json,sys; assert json.load(sys.stdin)["mode"] == "account"' 2>/dev/null; then
    READY=1
    break
  fi
  sleep 1
done
test "${READY:-}" = 1
ln -sfn /etc/nginx/sites-available/refit-platform /etc/nginx/sites-enabled/refit-platform
if ! nginx -t; then
  rm -f /etc/nginx/sites-enabled/refit-platform
  exit 1
fi
systemctl reload nginx
cat > /etc/systemd/system/refit-platform-certificate.service <<UNIT
[Unit]
Description=Renew Refit HTTPS certificate
[Service]
Type=oneshot
ExecStart=$CERTBOT renew --quiet --cert-name refit-platform-ip --deploy-hook "systemctl reload nginx"
UNIT
cat > /etc/systemd/system/refit-platform-certificate.timer <<'UNIT'
[Unit]
Description=Check Refit short-lived HTTPS certificate twice daily
[Timer]
OnCalendar=*-*-* 03,15:00:00
Persistent=true
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now refit-platform-certificate.timer
printf 'Refit platform ready at https://%s/\n' "$IP"
